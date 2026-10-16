"""Regression test: the plugin entrypoints import with ONLY declared dependencies.

The live runtime failed with ``No module named 'yaml'`` because PyYAML was used
but never declared (the test venv merely happened to have it). This test runs
each entrypoint in a fresh interpreter (``python -I``) behind an import guard
that refuses every top-level module which is neither

- stdlib (``sys.stdlib_module_names``),
- the plugin's own code (``spawn_session``),
- provided by a distribution declared in ``pyproject.toml``
  ``[project].dependencies`` (the list Hermes installs on consent), nor
- host-provided by the Hermes checkout (``HOST_PROVIDED``; replaced by stubs).

So any new undeclared third-party import fails here instead of in production.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Supplied by the Hermes checkout the plugin runs inside, never installed by
# the plugin's dependency step. fastapi: dashboard/plugin_api.py is only
# mounted by the Hermes dashboard/web server, which ships fastapi itself.
# Hermes-internal modules are replaced by stubs; HOST_REAL ones (fastapi) are
# imported for real before the guard is installed.
HOST_PROVIDED = frozenset(
    {"hermes_cli", "hermes_constants", "hermes_bootstrap", "tools", "gateway", "tui_gateway"}
)
HOST_REAL = ("fastapi",)


def declared_requirements() -> list[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return list(data.get("project", {}).get("dependencies", []))


def _dist_name(requirement: str) -> str:
    return re.split(r"[\s\[<>=!~;]", requirement, maxsplit=1)[0]


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def declared_top_level_modules() -> set[str]:
    """Top-level import names provided by the declared distributions."""
    wanted = {_norm(_dist_name(r)) for r in declared_requirements()}
    modules: set[str] = set()
    for module, dists in metadata.packages_distributions().items():
        if any(_norm(d) in wanted for d in dists):
            modules.add(module)
    return modules


_GUARD = r"""
import importlib.abc, importlib.util, sys, types

ALLOWED = set(json.loads(sys.argv[1]))
HOST = set(json.loads(sys.argv[2]))
ROOT = sys.argv[3]
TARGET = sys.argv[4]
for _host in json.loads(sys.argv[5]):
    __import__(_host)  # host-provided, loaded (with its own deps) before the guard


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None


class Guard(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        top = fullname.split(".")[0]
        if top in HOST:
            return importlib.util.spec_from_loader(fullname, self, is_package=True)
        if top in sys.stdlib_module_names or top in ALLOWED or fullname in sys.modules:
            return None
        raise ModuleNotFoundError(f"undeclared dependency: {fullname!r}", name=fullname)

    def create_module(self, spec):
        mod = _Stub(spec.name)
        mod.__path__ = []
        return mod

    def exec_module(self, module):
        pass


sys.meta_path.insert(0, Guard())

if TARGET == "register":
    _ns = types.ModuleType("hermes_plugins")
    _ns.__path__ = []
    sys.modules["hermes_plugins"] = _ns  # Hermes loads directory plugins under a namespace
    spec = importlib.util.spec_from_file_location(
        "hermes_plugins.spawn_session_entry", ROOT + "/__init__.py",
        submodule_search_locations=[ROOT],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert callable(mod.register)
else:
    spec = importlib.util.spec_from_file_location("spawn_session_plugin_api", ROOT + "/dashboard/plugin_api.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.router is not None
print("IMPORT_OK")
"""


def _run_isolated(target: str) -> subprocess.CompletedProcess[str]:
    allowed = sorted(declared_top_level_modules() | {"spawn_session", "hermes_plugins", "spawn_session_plugin_api"})
    code = "import json\n" + _GUARD
    return subprocess.run(
        [sys.executable, "-I", "-c", code, json.dumps(allowed), json.dumps(sorted(HOST_PROVIDED)), str(ROOT), target, json.dumps(list(HOST_REAL))],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
    )


def test_pyyaml_declared_with_upper_bound() -> None:
    reqs = {_norm(_dist_name(r)): r for r in declared_requirements()}
    assert "pyyaml" in reqs, "spawn_session/handover.py imports yaml; PyYAML must be declared"
    assert "<" in reqs["pyyaml"], "declare an upper bound (dependency security policy)"


def test_plugin_yaml_declares_no_competing_dependency_list() -> None:
    # pyproject.toml wins over plugin.yaml; a second list would silently drift.
    text = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    assert "python_dependencies" not in text and "pip_dependencies" not in text


@pytest.mark.parametrize("target", ["register", "plugin_api"])
def test_entrypoint_imports_with_only_declared_dependencies(target: str) -> None:
    for host in HOST_REAL:
        pytest.importorskip(host)
    proc = _run_isolated(target)
    assert proc.returncode == 0 and "IMPORT_OK" in proc.stdout, proc.stderr[-2000:]
