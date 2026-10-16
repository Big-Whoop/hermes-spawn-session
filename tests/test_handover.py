from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import yaml

from spawn_session import handover as ho

TZ = timezone(timedelta(hours=2))
NOW = datetime(2026, 10, 16, 16, 0, 0, tzinfo=TZ)


def _create(tmp_path, **kw):
    args: dict[str, Any] = dict(
        title="Fix flaky test",
        task="Make test_x stable.",
        context="CI fails 1 in 5 runs.\n\nSee log.",
        parent_session_id="ses_parent",
        model="anthropic:claude-opus",
        effort="medium",
        cwd="/repo",
        now=NOW,
    )
    args.update(kw)
    return ho.create(tmp_path / ".hermes" / "handovers", **args)


def test_create_writes_file_with_frontmatter(tmp_path):
    h = _create(tmp_path, worktree={"path": "/repo/.worktrees/x", "branch": "spawn/x"}, kanban_board="b")
    assert h.path == tmp_path / ".hermes/handovers/2026-10-16-fix-flaky-test.md"
    text = h.path.read_text()
    assert text.startswith("---\n")
    meta = yaml.safe_load(text.split("---\n")[1])
    assert meta["parent_session_id"] == "ses_parent"
    assert meta["child_session_id"] is None
    assert meta["status"] == "running"
    assert meta["model"] == "anthropic:claude-opus"
    assert meta["provider"] == "anthropic"
    assert meta["effort"] == "medium"
    assert meta["cwd"] == "/repo"
    assert meta["worktree"] == {"path": "/repo/.worktrees/x", "branch": "spawn/x"}
    assert meta["kanban_board"] == "b"
    assert meta["created_at"] == "2026-10-16T16:00:00+02:00"
    assert meta["reported_at"] is None
    assert meta["handover_id"].startswith("hs_20261016_")
    assert "# Task\nMake test_x stable." in text
    assert "# Context\nCI fails" in text
    assert "# Report" not in text


def test_create_dedupes_slug(tmp_path):
    a = _create(tmp_path)
    b = _create(tmp_path)
    c = _create(tmp_path)
    assert [p.path.name for p in (a, b, c)] == [
        "2026-10-16-fix-flaky-test.md",
        "2026-10-16-fix-flaky-test-2.md",
        "2026-10-16-fix-flaky-test-3.md",
    ]


@pytest.mark.parametrize(
    "kw",
    [
        {"model": "claude-opus"},  # bare model name (D6)
        {"status": "reported"},
        {"initiation": "whatever"},
        {"initiator": "robot"},
        {"worktree": {"path": "/x"}},
    ],
)
def test_create_validation(tmp_path, kw):
    with pytest.raises(ho.HandoverError):
        _create(tmp_path, **kw)


def test_slugify():
    assert ho.slugify("  Fix: Flaky Test!! ") == "fix-flaky-test"
    assert ho.slugify("äöü") == "handover"
    assert len(ho.slugify("a" * 200)) <= 48


def test_round_trip(tmp_path):
    h = _create(tmp_path, allowed_toolsets=["web", "file"], status="proposed")
    r = ho.read(h.path)
    assert r.meta == h.meta
    assert r.task == h.task
    assert r.context == h.context
    assert r.reports == []
    assert ho.render(r) == h.path.read_text()
    # parse(render(x)) is a fixpoint
    assert ho.render(ho.parse(ho.render(r))) == ho.render(r)


def test_parse_errors():
    with pytest.raises(ho.HandoverParseError):
        ho.parse("# Task\nno frontmatter")
    with pytest.raises(ho.HandoverParseError):
        ho.parse("---\nhandover_id: x\ntitle: t\nstatus: bogus\n---\n# Task\n\n# Context\n")
    with pytest.raises(ho.HandoverParseError):
        ho.parse("---\nhandover_id: x\ntitle: t\nstatus: running\n---\n# Task\nonly task\n")
    with pytest.raises(ho.HandoverParseError):
        ho.parse("---\nhandover_id: x\ntitle: t\nstatus: running\n---\n# Task\n\n# Context\n\n# Other\n")


VALID = [
    ("proposed", "running"),
    ("proposed", "abandoned"),
    ("running", "reported"),
    ("running", "abandoned"),
    ("running", "detached"),
    ("reported", "delivered"),
    ("reported", "detached"),
    ("delivered", "reported"),
    ("delivered", "detached"),
]


def test_transition_table_matches_spec():
    for src in ho.STATUSES:
        for dst in ho.STATUSES:
            assert ho.can_transition(src, dst) == ((src, dst) in VALID), (src, dst)
    assert all(not ho.TRANSITIONS[s] for s in ho.TERMINAL_STATUSES)


def test_update_status_records_history(tmp_path):
    h = _create(tmp_path, status="proposed")
    ho.update_status(h.path, "running", by="user", child_session_id="ses_child")
    r = ho.read(h.path)
    assert r.status == "running"
    assert r.meta["child_session_id"] == "ses_child"
    assert len(r.meta["history"]) == 1
    entry = r.meta["history"][0]
    assert (entry["from"], entry["to"], entry["by"]) == ("proposed", "running", "user")
    ho.update_status(h.path, "abandoned", reason="user aborted")
    r = ho.read(h.path)
    assert r.status == "abandoned"
    assert r.meta["history"][-1]["reason"] == "user aborted"


@pytest.mark.parametrize("terminal", ["abandoned", "detached"])
def test_terminal_states_reject_everything(tmp_path, terminal):
    h = _create(tmp_path)
    ho.update_status(h.path, terminal)
    for dst in ho.STATUSES:
        with pytest.raises(ho.InvalidTransition):
            ho.update_status(h.path, dst)
    with pytest.raises(ho.InvalidTransition):
        ho.append_report(h.path, "late")
    assert ho.read(h.path).status == terminal


def test_invalid_transition_leaves_file_untouched(tmp_path):
    h = _create(tmp_path, status="proposed")
    before = h.path.read_text()
    with pytest.raises(ho.InvalidTransition):
        ho.update_status(h.path, "delivered")
    with pytest.raises(ho.HandoverError):
        ho.update_status(h.path, "nonsense")
    assert h.path.read_text() == before


def test_append_report_and_follow_up(tmp_path):
    h = _create(tmp_path)
    body = ho.format_report("Fixed.", changes="tests/x.py", artifacts="PR #3")
    r = ho.append_report(h.path, body)
    assert r.status == "reported"
    assert r.meta["reported_at"]
    text = h.path.read_text()
    assert "# Report\n## Result\nFixed.\n\n## Changes\ntests/x.py\n\n## Open items\n-\n\n## Artifacts\nPR #3" in text
    assert ho.report_heading(r) == "Report"

    # SPEC 4.2: a follow-up before delivery is allowed; status stays reported.
    r = ho.append_report(h.path, ho.format_report("Before delivery."))
    assert r.status == "reported" and len(r.reports) == 2

    ho.update_status(h.path, "delivered")
    r = ho.append_report(h.path, ho.format_report("Follow-up."))
    assert r.status == "reported"
    assert len(r.reports) == 3
    assert "# Report (3)\n## Result\nFollow-up." in h.path.read_text()
    assert ho.report_heading(r) == "Report (3)"
    parsed = ho.read(h.path)
    assert parsed.reports == r.reports
    assert [e["to"] for e in parsed.meta["history"]] == ["reported", "reported", "delivered", "reported"]


def test_append_report_from_proposed_rejected(tmp_path):
    h = _create(tmp_path, status="proposed")
    with pytest.raises(ho.InvalidTransition):
        ho.append_report(h.path, "x")


def test_child_first_message_has_no_frontmatter(tmp_path):
    h = _create(tmp_path)
    msg = ho.child_first_message(h)
    assert msg.startswith("# Task\n")
    assert "# Context\n" in msg
    assert "parent_session_id" not in msg


def test_atomic_write_replaces_and_leaves_no_temp(tmp_path):
    p = tmp_path / "sub" / "f.md"
    ho.atomic_write_text(p, "one")
    ho.atomic_write_text(p, "two")
    assert p.read_text() == "two"
    assert [x.name for x in p.parent.iterdir()] == ["f.md"]


def test_atomic_write_failure_keeps_original(tmp_path, monkeypatch):
    p = tmp_path / "f.md"
    ho.atomic_write_text(p, "original")

    def boom(src, dst):
        raise OSError("disk on fire")

    monkeypatch.setattr(ho.os, "replace", boom)
    with pytest.raises(OSError):
        ho.atomic_write_text(p, "new")
    assert p.read_text() == "original"
    assert [x.name for x in tmp_path.iterdir()] == ["f.md"]


def test_update_status_is_atomic_on_failure(tmp_path, monkeypatch):
    h = _create(tmp_path)
    before = h.path.read_text()
    monkeypatch.setattr(ho.os, "replace", lambda s, d: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(OSError):
        ho.append_report(h.path, "r")
    assert h.path.read_text() == before
    assert sorted(x.name for x in h.path.parent.iterdir()) == [h.path.name]


# --------------------------------------------------------------------------- H1 escaping (review round 1)

H1_TASK = "Do the thing.\n# Heading in task\nmore\n\\# already escaped\n\\\\# double"
H1_CONTEXT = "# Top heading\nbody\n#not-a-heading\n  # indented"


def test_create_with_h1_lines_round_trips(tmp_path):
    h = _create(tmp_path, task=H1_TASK, context=H1_CONTEXT)
    back = ho.read(h.path)
    assert back.task == H1_TASK
    assert back.context == H1_CONTEXT
    text = h.path.read_text()
    assert "\n\\# Heading in task\n" in text
    assert "\n\\\\# already escaped\n" in text
    assert ho.render(back) == text  # render/parse fixpoint


def test_append_report_with_h1_then_deliver(tmp_path):
    h = _create(tmp_path)
    report = "## Result\nDone.\n\n# Summary\nextra"
    ho.append_report(h.path, report)
    back = ho.read(h.path)
    assert back.status == "reported"
    assert back.reports == [report]
    assert ho.update_status(h.path, "delivered").status == "delivered"
    ho.append_report(h.path, "# Report\nfollow-up")
    back = ho.read(h.path)
    assert back.reports == [report, "# Report\nfollow-up"]


def test_escape_unescape_inverse():
    for s in [H1_TASK, H1_CONTEXT, "", "# ", "plain"]:
        assert ho.unescape_body(ho.escape_body(s)) == s
