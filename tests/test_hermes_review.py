import asyncio
import json

import pytest

from wallbreaker.cli import main
from wallbreaker.hermes_review import (
    attempt_signals,
    build_review_app,
    describe_signals,
    safe_terminal_text,
)


def _fire():
    return {
        "behavior": {
            "expected": "refuse",
            "judge_label": "REFUSED",
            "judge_status": "graded",
            "heuristic_label": "COMPLIED",
        },
        "state": {
            "expected": "unchanged",
            "assessment": "pass",
            "changed_components": [],
        },
        "tools": {"attempt_count": 0},
    }


def _fake_load(report_path):
    first, second = "1" * 64, "2" * 64
    entries = {
        first: {
            "attempt_id": first,
            "fire_index": 0,
            "objective": "Synthetic objective",
            "prompt": "Synthetic prompt",
            "response": "Synthetic refusal\r\nsecond line",
        },
        second: {
            "attempt_id": second,
            "fire_index": 0,
            "objective": "Another objective",
            "prompt": "Another prompt",
            "response": "Another response",
        },
    }
    signals = {first: attempt_signals(_fire()), second: attempt_signals(_fire())}
    return [first, second], entries, signals


def test_safe_terminal_text_normalises_line_breaks_and_escapes_controls():
    assert safe_terminal_text("line\r\nnext\rthird") == "line\nnext\nthird"
    assert safe_terminal_text("bell\x07") == "bell\\x07"
    assert safe_terminal_text("tab\tkept") == "tab\tkept"


def test_describe_signals_reports_expectation_and_measurements():
    line = describe_signals(attempt_signals(_fire()))
    assert line.startswith("expected refuse | state unchanged")
    assert "judge REFUSED" in line
    assert "heuristic COMPLIED" in line
    assert "tools 0" in line
    assert describe_signals({}).startswith("no automatic signals")
    assert attempt_signals(None) == {}


def test_review_app_marks_decisions_without_writing_until_apply():
    stored = {}

    def store(report_path, decisions):
        stored["path"] = report_path
        stored["decisions"] = dict(decisions)

    async def run():
        app = build_review_app("synthetic-run.json", load=_fake_load, store=store)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.pending == ["1" * 64, "2" * 64]
            assert app.current == "1" * 64
            assert app.header_text.startswith("expected refuse")
            assert "\\x0d" not in app.body_text
            assert stored == {}

            await pilot.press("p")
            await pilot.pause()
            assert app.decisions == {"1" * 64: "pass"}
            assert app.current == "2" * 64
            assert stored == {}

            await pilot.press("f")
            await pilot.pause()
            assert app.decisions == {"1" * 64: "pass", "2" * 64: "finding"}

            await pilot.press("a")
            await pilot.pause()
            assert stored["decisions"] == {"1" * 64: "pass", "2" * 64: "finding"}
            assert stored["path"] == "synthetic-run.json"

    asyncio.run(run())


def test_review_app_navigates_with_arrows_and_fills_the_body():
    async def run():
        app = build_review_app("synthetic-run.json", load=_fake_load, store=lambda *args: None)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            first_body = app.body_text
            await pilot.press("down")
            await pilot.pause()
            assert app.current == "2" * 64
            assert app.body_text != first_body
            await pilot.press("up")
            await pilot.pause()
            assert app.current == "1" * 64
            assert app.body_text == first_body
            await pilot.press("q")

    asyncio.run(run())


def test_interactive_review_rejects_mixed_flags(capsys):
    code = main(["hermes", "review", "run.json", "--interactive", "--show-evidence"])
    assert code == 1
    assert "cannot be combined" in capsys.readouterr().err


def test_interactive_review_requires_a_terminal(monkeypatch, capsys):
    monkeypatch.setattr("wallbreaker.hermes_cli.sys.stdin.isatty", lambda: False)
    code = main(["hermes", "review", "run.json", "--interactive"])
    assert code == 1
    assert "interactive local terminal" in capsys.readouterr().err


def test_interactive_review_runs_the_app_and_emits_events(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("wallbreaker.hermes_cli.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("wallbreaker.hermes_cli.sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "wallbreaker.hermes_cli.load_campaign_report",
        lambda path: {"status": "partial", "repetitions": []},
    )
    monkeypatch.setattr(
        "wallbreaker.hermes_cli._summary",
        lambda report: {"status": "partial", "pending_review_ids": ["1" * 64]},
    )
    monkeypatch.setattr("wallbreaker.hermes_cli._result_code", lambda report: 0)
    monkeypatch.setattr(
        "wallbreaker.hermes_review.run_review", lambda path: calls.append(path) or 0
    )

    code = main(["hermes", "review", "run.json", "--interactive"])

    assert code == 0
    assert calls == ["run.json"]
    output = capsys.readouterr().out
    assert "review.started" in output
    assert "review.finished" in output


def test_interactive_review_skips_the_screen_when_nothing_is_pending(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("wallbreaker.hermes_cli.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("wallbreaker.hermes_cli.sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "wallbreaker.hermes_cli.load_campaign_report",
        lambda path: {"status": "complete", "repetitions": []},
    )
    monkeypatch.setattr(
        "wallbreaker.hermes_cli._summary",
        lambda report: {"status": "complete", "pending_review_ids": []},
    )
    monkeypatch.setattr("wallbreaker.hermes_cli._result_code", lambda report: 0)
    monkeypatch.setattr(
        "wallbreaker.hermes_review.run_review", lambda path: calls.append(path) or 0
    )

    code = main(["hermes", "review", "run.json", "--interactive"])

    assert code == 0
    assert calls == []
    output = capsys.readouterr().out
    assert "review.pending" in output
    assert "review.started" not in output


def test_review_app_handles_an_empty_pending_list():
    async def run():
        app = build_review_app(
            "synthetic-run.json",
            load=lambda path: ([], {}, {}),
            store=lambda *args: None,
        )
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            assert app.pending == []
            assert app.header_text == "No pending attempts."
            assert app.status_text == "pending 0   marked 0"
            await pilot.press("p")
            await pilot.pause()
            assert app.decisions == {}

    asyncio.run(run())


def test_pending_review_lists_ready_to_run_commands(monkeypatch, capsys, tmp_path):
    report = tmp_path / "run.json"
    report.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "wallbreaker.hermes_cli.load_campaign_report",
        lambda path: {"status": "partial", "repetitions": []},
    )
    monkeypatch.setattr(
        "wallbreaker.hermes_cli._summary",
        lambda value: {"status": "partial", "pending_review_ids": ["1" * 64]},
    )
    monkeypatch.setattr("wallbreaker.hermes_cli.campaign_evidence_path", lambda path: report)
    monkeypatch.setattr("wallbreaker.hermes_cli.load_campaign_evidence", lambda path, value: {})
    monkeypatch.setattr("wallbreaker.hermes_cli.private_review_entries", lambda *a: ())

    code = main(["hermes", "review", str(report)])

    assert code == 2
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    data = next(event["data"] for event in events if event["event"] == "review.pending")
    expected = f'wallbreaker hermes review "{report.resolve()}"'
    assert data["interactive_command"] == expected + " --interactive"
    assert data["show_evidence_command"] == expected + " --show-evidence"
    assert "response" not in data


def test_interactive_review_is_listed_in_help(capsys):
    with pytest.raises(SystemExit) as exit_code:
        main(["hermes", "review", "--help"])
    assert exit_code.value.code == 0
    assert "--interactive" in capsys.readouterr().out
