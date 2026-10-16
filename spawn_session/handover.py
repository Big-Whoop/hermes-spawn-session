"""Handover file format and read/write library (SPEC.md section 5, decisions D5/D11).

A handover file lives at ``<cwd>/.hermes/handovers/YYYY-MM-DD-<slug>.md`` and
consists of YAML frontmatter followed by ``# Task``, ``# Context`` and zero or
more appended ``# Report`` sections (``# Report``, ``# Report (2)``, ...).

All writes are atomic: content is written to a temporary file in the target
directory, fsynced, then moved into place with ``os.replace``.

Free-text contract: task, context and report bodies may contain arbitrary
markdown, including H1 lines (``# Heading``). Because H1 headings delimit the
file's sections, body lines starting with ``# `` are escaped on write by
prefixing a backslash (``\\# Heading``, which markdown renders as a literal
``# Heading``); lines already starting with backslashes followed by ``# `` get
one more backslash. Parsing strips exactly one backslash again, so the
in-memory text round-trips losslessly and files on disk always parse.
"""

from __future__ import annotations

import os
import re
import secrets
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

STATUSES = ("proposed", "running", "reported", "delivered", "abandoned", "detached")
TERMINAL_STATUSES = frozenset({"abandoned", "detached"})

# Allowed transitions (SPEC.md section 6).
TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"running", "abandoned"}),
    "running": frozenset({"reported", "abandoned", "detached"}),
    "reported": frozenset({"delivered", "detached"}),
    "delivered": frozenset({"reported", "detached"}),
    "abandoned": frozenset(),
    "detached": frozenset(),
}

INITIATIONS = ("user_asked", "own_initiative")
INITIATORS = ("agent", "user")

DEFAULT_HANDOVER_DIR = Path(".hermes") / "handovers"

# Report subsections in canonical order.
REPORT_SUBSECTIONS = ("Result", "Changes", "Open items", "Artifacts")

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)
_H1_RE = re.compile(r"^# (.+?)\s*$", re.MULTILINE)
_REPORT_HEADING_RE = re.compile(r"^Report(?: \((\d+)\))?$")
_ESCAPE_RE = re.compile(r"^(\\*# )", re.MULTILINE)
_UNESCAPE_RE = re.compile(r"^\\(\\*# )", re.MULTILINE)

# Frontmatter key order used when writing.
_KEY_ORDER = (
    "handover_id",
    "parent_session_id",
    "child_session_id",
    "title",
    "status",
    "initiation",
    "initiator",
    "model",
    "provider",
    "effort",
    "cwd",
    "worktree",
    "kanban_board",
    "allowed_toolsets",
    "created_at",
    "updated_at",
    "reported_at",
    "history",
)


class HandoverError(Exception):
    """Base error for handover file operations."""


class InvalidTransition(HandoverError):
    """Raised when a status change is not allowed by the state machine."""


class HandoverParseError(HandoverError):
    """Raised when a handover file cannot be parsed."""


@dataclass
class Handover:
    """In-memory representation of a handover file."""

    meta: dict[str, Any]
    task: str
    context: str
    reports: list[str] = field(default_factory=list)
    path: Path | None = None

    @property
    def status(self) -> str:
        return self.meta["status"]

    @property
    def handover_id(self) -> str:
        return self.meta["handover_id"]

    @property
    def title(self) -> str:
        return self.meta["title"]


# --------------------------------------------------------------------------- helpers


def _now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def slugify(title: str, max_len: int = 48) -> str:
    """Lowercase ASCII slug from a title; never empty."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    slug = slug[:max_len].rstrip("-")
    return slug or "handover"


def new_handover_id(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"hs_{now:%Y%m%d}_{secrets.token_hex(3)}"


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp file + fsync + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    try:  # make the rename durable; best effort on platforms without dir fds
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def handover_path(base_dir: Path, title: str, date: datetime | None = None) -> Path:
    """Return a non-existing ``YYYY-MM-DD-<slug>.md`` path, de-duplicated with -2, -3, ..."""
    date = date or datetime.now()
    stem = f"{date:%Y-%m-%d}-{slugify(title)}"
    candidate = Path(base_dir) / f"{stem}.md"
    n = 2
    while candidate.exists():
        candidate = Path(base_dir) / f"{stem}-{n}.md"
        n += 1
    return candidate


# --------------------------------------------------------------------------- render / parse


def escape_body(text: str) -> str:
    """Escape body lines that would otherwise be parsed as H1 section headings."""
    return _ESCAPE_RE.sub(r"\\\1", text)


def unescape_body(text: str) -> str:
    """Inverse of :func:`escape_body`."""
    return _UNESCAPE_RE.sub(r"\1", text)


def _ordered_meta(meta: dict[str, Any]) -> dict[str, Any]:
    ordered = {k: meta[k] for k in _KEY_ORDER if k in meta}
    ordered.update({k: v for k, v in meta.items() if k not in ordered})
    return ordered


def render(h: Handover) -> str:
    front = yaml.safe_dump(
        _ordered_meta(h.meta), sort_keys=False, allow_unicode=True, default_flow_style=False
    ).rstrip("\n")
    parts = [
        f"---\n{front}\n---\n",
        f"# Task\n{escape_body(h.task.strip())}\n",
        f"# Context\n{escape_body(h.context.strip())}\n",
    ]
    for i, body in enumerate(h.reports, start=1):
        heading = "Report" if i == 1 else f"Report ({i})"
        parts.append(f"# {heading}\n{escape_body(body.strip())}\n")
    return "\n".join(parts)


def parse(text: str, path: Path | None = None) -> Handover:
    m = _FRONTMATTER_RE.match(text.replace("\r\n", "\n"))
    if not m:
        raise HandoverParseError("missing YAML frontmatter")
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise HandoverParseError(f"invalid frontmatter: {exc}") from exc
    if not isinstance(meta, dict):
        raise HandoverParseError("frontmatter is not a mapping")
    for key in ("handover_id", "title", "status"):
        if key not in meta:
            raise HandoverParseError(f"frontmatter missing {key!r}")
    if meta["status"] not in STATUSES:
        raise HandoverParseError(f"unknown status {meta['status']!r}")

    body = m.group(2)
    headings = list(_H1_RE.finditer(body))
    sections: list[tuple[str, str]] = []
    for i, hm in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        sections.append((hm.group(1), unescape_body(body[hm.end():end].strip("\n"))))

    task = context = None
    reports: list[str] = []
    for name, content in sections:
        if name == "Task" and task is None:
            task = content
        elif name == "Context" and context is None:
            context = content
        elif _REPORT_HEADING_RE.match(name):
            reports.append(content)
        else:
            raise HandoverParseError(f"unexpected section {name!r}")
    if task is None or context is None:
        raise HandoverParseError("missing Task or Context section")
    return Handover(meta=meta, task=task, context=context, reports=reports, path=path)


# --------------------------------------------------------------------------- public API


def create(
    base_dir: Path | str,
    *,
    title: str,
    task: str,
    context: str,
    parent_session_id: str,
    model: str,
    provider: str | None = None,
    effort: str | None = None,
    cwd: str | None = None,
    child_session_id: str | None = None,
    status: str = "running",
    initiation: str = "user_asked",
    initiator: str = "agent",
    worktree: dict[str, str] | None = None,
    kanban_board: str | None = None,
    allowed_toolsets: list[str] | None = None,
    now: datetime | None = None,
) -> Handover:
    """Create a new handover file in ``base_dir`` and return it.

    ``model`` must use ``provider:model`` syntax (D6); ``provider`` defaults to
    the prefix of ``model``.
    """
    if status not in ("proposed", "running"):
        raise HandoverError("new handovers start as 'proposed' or 'running'")
    if initiation not in INITIATIONS:
        raise HandoverError(f"initiation must be one of {INITIATIONS}")
    if initiator not in INITIATORS:
        raise HandoverError(f"initiator must be one of {INITIATORS}")
    if ":" not in model:
        raise HandoverError("model must use 'provider:model' syntax")
    if worktree is not None and not {"path", "branch"} <= set(worktree):
        raise HandoverError("worktree needs 'path' and 'branch'")

    now = now or datetime.now().astimezone()
    ts = now.replace(microsecond=0).isoformat()
    meta: dict[str, Any] = {
        "handover_id": new_handover_id(now),
        "parent_session_id": parent_session_id,
        "child_session_id": child_session_id,
        "title": title,
        "status": status,
        "initiation": initiation,
        "initiator": initiator,
        "model": model,
        "provider": provider or model.split(":", 1)[0],
        "effort": effort,
        "cwd": cwd or os.getcwd(),
        "worktree": dict(worktree) if worktree else None,
        "kanban_board": kanban_board,
        "allowed_toolsets": list(allowed_toolsets) if allowed_toolsets is not None else None,
        "created_at": ts,
        "updated_at": ts,
        "reported_at": None,
        "history": [],
    }
    h = Handover(meta=meta, task=task, context=context)
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    # Exclusive create guards against a race on the de-duplicated name.
    while True:
        path = handover_path(base, title, now)
        try:
            with open(path, "x", encoding="utf-8"):
                pass
            break
        except FileExistsError:
            continue
    h.path = path
    atomic_write_text(path, render(h))
    return h


def read(path: Path | str) -> Handover:
    path = Path(path)
    return parse(path.read_text(encoding="utf-8"), path=path)


def write(h: Handover) -> None:
    if h.path is None:
        raise HandoverError("handover has no path")
    atomic_write_text(h.path, render(h))


def can_transition(src: str, dst: str) -> bool:
    return dst in TRANSITIONS.get(src, frozenset())


def update_status(
    path: Path | str,
    new_status: str,
    *,
    by: str = "agent",
    reason: str | None = None,
    child_session_id: str | None = None,
) -> Handover:
    """Move a handover to ``new_status``, recording a history entry."""
    if new_status not in STATUSES:
        raise HandoverError(f"unknown status {new_status!r}")
    h = read(path)
    old = h.status
    if not can_transition(old, new_status):
        raise InvalidTransition(f"{old} -> {new_status} not allowed")
    ts = _now()
    entry: dict[str, Any] = {"at": ts, "from": old, "to": new_status, "by": by}
    if reason:
        entry["reason"] = reason
    h.meta.setdefault("history", []).append(entry)
    h.meta["status"] = new_status
    h.meta["updated_at"] = ts
    if child_session_id is not None:
        h.meta["child_session_id"] = child_session_id
    write(h)
    return h


def format_report(
    result: str,
    changes: str | None = None,
    open_items: str | None = None,
    artifacts: str | None = None,
) -> str:
    """Build a Report body with the canonical subsections."""
    values = (result, changes, open_items, artifacts)
    return "\n\n".join(
        f"## {name}\n{(v or '-').strip()}" for name, v in zip(REPORT_SUBSECTIONS, values)
    )


def append_report(
    path: Path | str,
    report: str,
    *,
    by: str = "agent",
) -> Handover:
    """Append a Report section and move the handover to ``reported``.

    Allowed from ``running`` (first report), ``delivered`` (follow-up,
    rendered as ``# Report (2)`` etc.) and ``reported`` (a follow-up written
    before the previous report was delivered; status stays ``reported``).
    """
    h = read(path)
    if h.status != "reported" and not can_transition(h.status, "reported"):
        raise InvalidTransition(f"cannot report from status {h.status!r}")
    ts = _now()
    h.reports.append(report)
    h.meta.setdefault("history", []).append(
        {"at": ts, "from": h.status, "to": "reported", "by": by}
    )
    h.meta["status"] = "reported"
    h.meta["updated_at"] = ts
    h.meta["reported_at"] = ts
    write(h)
    return h


def report_heading(h: Handover, index: int | None = None) -> str:
    """Heading of report ``index`` (1-based; default latest)."""
    i = index or len(h.reports)
    return "Report" if i == 1 else f"Report ({i})"


def child_first_message(h: Handover) -> str:
    """Body sent to the child session as its first message (no frontmatter)."""
    return f"# Task\n{h.task.strip()}\n\n# Context\n{h.context.strip()}\n"
