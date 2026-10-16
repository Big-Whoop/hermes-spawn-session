"""Import audit: every third-party import must be a declared dependency.

Regression for the live failure ``No module named 'yaml'`` (card t_bdfc5a97):
Hermes installs only the dependencies a plugin declares, so a package that
merely happens to be present in the dev venv must not be relied upon.

Two checks:

1. Static: walk the AST of every plugin module and compare each top-level
   import against stdlib + declared deps + host-provided Hermes modules.
2. Dynamic: import every plugin module in a fresh interpreter whose import
   system refuses any top-level module that is neither stdlib, declared, nor
   local — so an undeclared package fails even if it is installed here.

``scripts/check_clean_venv.sh`` additionally imports everything in a brand-new
venv containing only the declared dependencies (needs network).
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Hermes core modules, provided by the host process and imported lazily
# inside try/except. They are not PyPI dependencies of the plugin.
HOST_MODULES = frozenset({"hermes_cli", "hermes_constants", "tools", "gateway", "tui_gateway"})

# Local top-level names (the plugin's own package).
LOCAL_MODULES = frozenset({"spawn_session", "spawn_session_plugin", "plugin_api"})

# Distribution name -> import name, for declared deps whose names differ.
DIST_TO_IMPORT = {"pyyaml": "yaml"}


def _req_name(req: str) -> str:
    return re.split(r"[\s<>=!~;\[]", req.strip(), maxsplit=1)[0].lower().replace("_", "-")


def _pyproject_deps() -> list[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


def _manifest_deps() -> list[str]:
    data = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    return list(data.get("python_dependencies") or [])


def declared_import_names() -> set[str]:
    names = set()
    for req in _pyproject_deps():
        dist = _req_name(req)
        names.add(DIST_TO_IMPORT.get(dist, dist.replace("-", "_")))
    return names


def plugin_modules() -> list[Path]:
    files = [ROOT / "__init__.py", *sorted((ROOT / "spawn_session").glob("*.py"))]
    files += sorted((ROOT / "dashboard").glob("*.py"))
    return files


def top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_manifest_and_pyproject_declare_the_same_deps():
    assert sorted(_manifest_deps()) == sorted(_pyproject_deps())


def test_every_dependency_has_an_upper_bound():
    for req in _pyproject_deps():
        assert "<" in req, f"{req!r}: add an upper bound (Hermes dependency policy)"


def test_no_undeclared_third_party_imports():
    allowed = set(sys.stdlib_module_names) | declared_import_names() | HOST_MODULES | LOCAL_MODULES
    allowed.add("__future__")
    offenders = {
        str(p.relative_to(ROOT)): sorted(top_level_imports(p) - allowed) for p in plugin_modules()
    }
    offenders = {k: v for k, v in offenders.items() if v}
    assert not offenders, f"undeclared imports (declare them in pyproject.toml + plugin.yaml): {offenders}"


def test_all_modules_import_with_only_declared_packages():
    allowed = sorted(declared_import_names() | LOCAL_MODULES)
    script = textwrap.dedent(
        f"""
        import importlib, importlib.util, sys
        from pathlib import Path

        LOCAL = set({sorted(LOCAL_MODULES)!r})
        ALLOWED = set({allowed!r}) | set(sys.stdlib_module_names) | {{"__future__"}}

        class Blocker:
            def find_spec(self, name, path=None, target=None):
                top = name.split(".")[0]
                if top not in ALLOWED:
                    raise ModuleNotFoundError(f"undeclared module {{name!r}}", name=name)
                return None

        # Declared packages may pull in their own (transitive) dependencies:
        # import them before arming the blocker so those are already loaded.
        for dep in ALLOWED - LOCAL - set(sys.stdlib_module_names):
            if dep != "__future__":
                importlib.import_module(dep)
        ALLOWED |= {{m.split(".")[0] for m in sys.modules}}
        sys.meta_path.insert(0, Blocker())

        root = Path({str(ROOT)!r})
        sys.path.insert(0, str(root))
        for p in sorted((root / "spawn_session").glob("*.py")):
            if p.stem != "__init__":
                importlib.import_module(f"spawn_session.{{p.stem}}")
        importlib.import_module("spawn_session")
        spec = importlib.util.spec_from_file_location(
            "spawn_session_plugin", root / "__init__.py",
            submodule_search_locations=[str(root)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules["spawn_session_plugin"] = mod
        spec.loader.exec_module(mod)
        spec = importlib.util.spec_from_file_location("plugin_api", root / "dashboard" / "plugin_api.py")
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        print("OK")
        """
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stderr[-3000:]


def test_blocker_catches_an_undeclared_import(tmp_path):
    """Sanity check of the dynamic audit: a module importing an undeclared
    package (here pytest, installed but not declared) must fail."""
    (tmp_path / "bad.py").write_text("import pytest\n", encoding="utf-8")
    script = textwrap.dedent(
        f"""
        import sys
        ALLOWED = set(sys.stdlib_module_names)
        class Blocker:
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] not in ALLOWED and name != "bad":
                    raise ModuleNotFoundError(name, name=name)
        sys.meta_path.insert(0, Blocker())
        sys.path.insert(0, {str(tmp_path)!r})
        import bad
        """
    )
    proc = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True)
    assert proc.returncode != 0 and "ModuleNotFoundError" in proc.stderr
