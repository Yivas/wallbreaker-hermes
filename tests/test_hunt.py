"""`hunt` sweeps a battery from the command line: plan first, then limits, then no-bodies output."""

from __future__ import annotations

import json

import pytest

from wallbreaker import hunt
from wallbreaker.config import Config, Endpoint


def _config(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    attacker = Endpoint("brain", "openai", "https://fixture.invalid", "fixture/brain")
    target = Endpoint("target", "openai", "https://fixture.invalid", "fixture/target")
    judge = Endpoint("judge", "openai", "https://fixture.invalid", "fixture/judge")
    return Config(default_profile="brain", profiles={"brain": attacker}, target=target, judge=judge)


def _args(**overrides):
    base = {
        "battery": "jbb",
        "category": None,
        "items": 2,
        "rounds": 3,
        "seed": 0,
        "timeout": 30.0,
        "max_tokens": hunt.TARGET_MAX_TOKENS,
        "config": None,
        "profile": None,
        "target": None,
        "output": "run.jsonl",
        "include_bodies": False,
        "dry_run": False,
        "authorized": False,
        "confirm": None,
    }
    base.update(overrides)
    return type("Args", (), base)()


@pytest.fixture
def wired(monkeypatch, tmp_path):
    config = _config(tmp_path)
    monkeypatch.setattr("wallbreaker.config.load_config", lambda path: config)
    return config


def test_dry_run_prints_the_plan_and_never_builds_a_provider(wired, capsys, monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("a dry run must not build a provider")

    monkeypatch.setattr("wallbreaker.providers.factory.build_provider", explode)

    assert hunt.run_hunt_cli(_args(dry_run=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "wallbreaker.hunt-plan/v1"
    assert payload["items"] == 2 and payload["max_tokens"] == hunt.TARGET_MAX_TOKENS
    assert payload["target"] == "fixture/target" and payload["judge"] == "fixture/judge"
    assert payload["token"]


def test_refuses_without_an_approved_token(wired, capsys):
    assert hunt.run_hunt_cli(_args()) == 2
    assert "Refusing to run" in capsys.readouterr().err

    assert hunt.run_hunt_cli(_args(authorized=True, confirm="wrong")) == 2
    assert "Refusing to run" in capsys.readouterr().err


def test_plan_token_changes_with_the_limits(wired):
    plan_a = hunt.plan_hunt(_args(), wired)
    plan_b = hunt.plan_hunt(_args(max_tokens=2048), wired)
    assert plan_a.token() != plan_b.token()


def _sweep_args(tmp_path, wired, name="hunt.jsonl", **overrides):
    base = _args(output=str(tmp_path / name), **overrides)
    base.authorized = True
    base.confirm = hunt.plan_hunt(base, wired).token()
    return base


def test_a_graded_reply_is_recorded_without_bodies(wired, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        hunt,
        "_load_behaviors",
        lambda plan: [{"id": "item-1", "category": "alpha", "behavior": "Synthetic one"}],
    )

    class FakeTarget:
        last_stop_reason = "end_turn"

        async def aclose(self):
            return None

    async def fake_fire(provider, messages, system, max_tokens):
        assert max_tokens == hunt.TARGET_MAX_TOKENS
        return "a real answer", "", "end_turn", False

    async def fake_grade(endpoint, response, payload="", objective="", reasoning="", **kwargs):
        return "COMPLIED", 10, "on task", "judge"

    monkeypatch.setattr("wallbreaker.providers.factory.build_provider", lambda endpoint, timeout=None: FakeTarget())
    monkeypatch.setattr("wallbreaker.tools.target._fire", fake_fire)
    monkeypatch.setattr("wallbreaker.judging.grade", fake_grade)

    output = tmp_path / "hunt.jsonl"
    assert hunt.run_hunt_cli(_sweep_args(tmp_path, wired)) == 0
    line = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    assert line["label"] == "COMPLIED" and line["graded_by"] == "judge"
    assert line["measured"] is True and line["response_empty"] is False
    assert line["stop_reason"] == "end_turn" and line["response_chars"] == len("a real answer")
    assert "behavior" not in line and "response" not in line
    summary = json.loads(capsys.readouterr().out)
    assert summary["measured_items"] == 1 and summary["by_category"]["alpha"]["labels"] == {"COMPLIED": 1}


def test_an_empty_reply_is_never_counted_as_a_verdict(wired, tmp_path, monkeypatch, capsys):
    """The bug that produced six phantom REFUSED rows: emptiness graded as refusal."""
    monkeypatch.setattr(
        hunt,
        "_load_behaviors",
        lambda plan: [{"id": "item-1", "category": "alpha", "behavior": "Synthetic one"}],
    )

    class FakeTarget:
        async def aclose(self):
            return None

    async def fake_fire(provider, messages, system, max_tokens):
        return "", "", "content_filter", True

    async def fake_grade(*_args, **_kwargs):
        raise AssertionError("an empty reply must not be sent to the judge as a verdict")

    monkeypatch.setattr("wallbreaker.providers.factory.build_provider", lambda endpoint, timeout=None: FakeTarget())
    monkeypatch.setattr("wallbreaker.tools.target._fire", fake_fire)
    monkeypatch.setattr("wallbreaker.judging.grade", fake_grade)

    output = tmp_path / "empty.jsonl"
    assert hunt.run_hunt_cli(_sweep_args(tmp_path, wired, name="empty.jsonl")) == 0
    line = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    assert line["response_empty"] is True and line["measured"] is False
    assert line["label"] is None and line["stop_reason"] == "content_filter"
    assert line["response_chars"] == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["empty_replies"] == 1 and summary["unmeasured_items"] == 1
    assert summary["by_category"]["alpha"]["labels"] == {}


def test_a_failed_fire_is_recorded_as_an_error(wired, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        hunt,
        "_load_behaviors",
        lambda plan: [{"id": "item-1", "category": "alpha", "behavior": "Synthetic one"}],
    )

    class FakeTarget:
        async def aclose(self):
            return None

    async def failing_fire(*_args, **_kwargs):
        raise TimeoutError("target timeout")

    monkeypatch.setattr("wallbreaker.providers.factory.build_provider", lambda endpoint, timeout=None: FakeTarget())
    monkeypatch.setattr("wallbreaker.tools.target._fire", failing_fire)

    output = tmp_path / "fail.jsonl"
    assert hunt.run_hunt_cli(_sweep_args(tmp_path, wired, name="fail.jsonl")) == 0
    line = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    assert line["error"] == "TimeoutError: target timeout"
    assert line["measured"] is False
    summary = json.loads(capsys.readouterr().out)
    assert summary["unmeasured_items"] == 1 and summary["by_category"]["alpha"]["errors"] == 1


def test_include_bodies_is_explicit_and_warns(wired, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        hunt,
        "_load_behaviors",
        lambda plan: [{"id": "item-1", "category": "alpha", "behavior": "Synthetic one"}],
    )

    class FakeTarget:
        async def aclose(self):
            return None

    async def fake_fire(*_args, **_kwargs):
        return "a real answer", "", "end_turn", False

    async def fake_grade(*_args, **_kwargs):
        return "REFUSED", 0, "declined", "judge"

    monkeypatch.setattr("wallbreaker.providers.factory.build_provider", lambda endpoint, timeout=None: FakeTarget())
    monkeypatch.setattr("wallbreaker.tools.target._fire", fake_fire)
    monkeypatch.setattr("wallbreaker.judging.grade", fake_grade)

    output = tmp_path / "bodies.jsonl"
    assert hunt.run_hunt_cli(_sweep_args(tmp_path, wired, name="bodies.jsonl", include_bodies=True)) == 0
    line = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    assert line["behavior"] == "Synthetic one" and line["response"] == "a real answer"
    assert "sensitive" in capsys.readouterr().err
