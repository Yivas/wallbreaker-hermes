"""`attack` fires a fixed battery of packagings at one objective, with no agent deciding."""

from __future__ import annotations

import json

import pytest

from wallbreaker import attack
from wallbreaker.config import Config, Endpoint


def _config(tmp_path):
    attacker = Endpoint("brain", "openai", "https://fixture.invalid", "fixture/brain")
    target = Endpoint("target", "openai", "https://fixture.invalid", "fixture/target")
    judge = Endpoint("judge", "openai", "https://fixture.invalid", "fixture/judge")
    return Config(default_profile="brain", profiles={"brain": attacker}, target=target, judge=judge)


def _args(**overrides):
    base = {
        "objective": "Synthetic objective",
        "objective_file": None,
        "persona": None,
        "transforms": [],
        "no_transforms": False,
        "prefill": False,
        "turns": 1,
        "max_tokens": attack.DEFAULT_MAX_TOKENS,
        "timeout": 90.0,
        "keep_going": False,
        "config": None,
        "target": None,
        "output": "attack.jsonl",
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


def test_dry_run_lists_the_packagings_and_builds_nothing(wired, capsys, monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("a dry run must not build a provider")

    monkeypatch.setattr("wallbreaker.providers.factory.build_provider", explode)

    assert attack.run_attack_cli(_args(prefill=True, turns=2, dry_run=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["packagings"] == [
        "plain", "encoded:base64", "encoded:rot13", "prefill", "prefill:past_round",
    ]
    assert payload["turns"] == 2 and payload["max_fires"] == 10
    assert payload["token"]


def test_refuses_without_an_approved_token(wired, capsys):
    assert attack.run_attack_cli(_args()) == 2
    assert "Refusing to run" in capsys.readouterr().err


def test_token_changes_with_the_battery(wired):
    plan_a = attack.plan_attack(_args(), wired, "Synthetic objective")
    plan_b = attack.plan_attack(_args(prefill=True), wired, "Synthetic objective")
    assert plan_a.token() != plan_b.token()


def test_missing_objective_is_a_usage_error(wired, capsys):
    assert attack.run_attack_cli(_args(objective="")) == 2
    assert "objective" in capsys.readouterr().err


def _sweep_args(tmp_path, wired, **overrides):
    base = _args(output=str(tmp_path / "attack.jsonl"), **overrides)
    base.authorized = True
    base.confirm = attack.plan_attack(base, wired, base.objective).token()
    return base


class _FakeProvider:
    async def aclose(self):
        return None


def test_stops_at_the_first_compliant_packaging(wired, tmp_path, monkeypatch, capsys):
    calls = []

    async def fake_fire(provider, messages, system, max_tokens):
        calls.append(len(messages))
        return "a real answer", "", "end_turn", False

    async def fake_grade(*_args, **_kwargs):
        return "COMPLIED", 10, "on task", "judge"

    monkeypatch.setattr("wallbreaker.providers.factory.build_provider", lambda endpoint, timeout=None: _FakeProvider())
    monkeypatch.setattr("wallbreaker.tools._util.complete_untruncated", fake_fire)
    monkeypatch.setattr("wallbreaker.judging.grade", fake_grade)

    output = tmp_path / "attack.jsonl"
    assert attack.run_attack_cli(_sweep_args(tmp_path, wired, no_transforms=True)) == 0
    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1, "a compliance should stop the battery by default"
    assert lines[0]["packaging"] == "plain" and lines[0]["label"] == "COMPLIED"
    assert lines[0]["measured"] is True
    summary = json.loads(capsys.readouterr().out)
    assert summary["complied_packagings"] == ["plain"] and summary["labels"] == {"COMPLIED": 1}


def test_keep_going_fires_the_whole_battery(wired, tmp_path, monkeypatch, capsys):
    async def fake_fire(*_args, **_kwargs):
        return "a real answer", "", "end_turn", False

    async def fake_grade(*_args, **_kwargs):
        return "COMPLIED", 10, "on task", "judge"

    monkeypatch.setattr("wallbreaker.providers.factory.build_provider", lambda endpoint, timeout=None: _FakeProvider())
    monkeypatch.setattr("wallbreaker.tools._util.complete_untruncated", fake_fire)
    monkeypatch.setattr("wallbreaker.judging.grade", fake_grade)

    output = tmp_path / "attack.jsonl"
    args = _sweep_args(tmp_path, wired, no_transforms=True, prefill=True, turns=2, keep_going=True)
    assert attack.run_attack_cli(args) == 0
    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 6, "3 packagings x 2 turns"
    assert {line["packaging"] for line in lines} == {"plain", "prefill", "prefill:past_round"}
    assert {line["turn"] for line in lines} == {1, 2}


def test_an_empty_reply_is_not_a_verdict(wired, tmp_path, monkeypatch, capsys):
    async def fake_fire(*_args, **_kwargs):
        return "", "", "length", True

    async def fake_grade(*_args, **_kwargs):
        raise AssertionError("an empty reply must not be graded as a verdict")

    monkeypatch.setattr("wallbreaker.providers.factory.build_provider", lambda endpoint, timeout=None: _FakeProvider())
    monkeypatch.setattr("wallbreaker.tools._util.complete_untruncated", fake_fire)
    monkeypatch.setattr("wallbreaker.judging.grade", fake_grade)

    output = tmp_path / "attack.jsonl"
    assert attack.run_attack_cli(_sweep_args(tmp_path, wired, no_transforms=True, turns=2)) == 0
    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1, "an empty reply ends the thread instead of being fed back"
    line = lines[0]
    assert line["response_empty"] is True and line["measured"] is False
    assert line["label"] is None and line["stop_reason"] == "length"
    summary = json.loads(capsys.readouterr().out)
    assert summary["labels"] == {} and summary["empty_replies"] == 1


def test_a_failing_fire_is_recorded_and_does_not_stop_the_battery(wired, tmp_path, monkeypatch, capsys):
    calls = {"n": 0}

    async def flaky_fire(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("target timeout")
        return "a real answer", "", "end_turn", False

    async def fake_grade(*_args, **_kwargs):
        return "REFUSED", 0, "declined", "judge"

    monkeypatch.setattr("wallbreaker.providers.factory.build_provider", lambda endpoint, timeout=None: _FakeProvider())
    monkeypatch.setattr("wallbreaker.tools._util.complete_untruncated", flaky_fire)
    monkeypatch.setattr("wallbreaker.judging.grade", fake_grade)

    output = tmp_path / "attack.jsonl"
    assert attack.run_attack_cli(_sweep_args(tmp_path, wired, no_transforms=True, prefill=True)) == 0
    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["error"] == "TimeoutError: target timeout"
    assert lines[0]["measured"] is False
    assert len(lines) == 3, "the remaining packagings still run"
    summary = json.loads(capsys.readouterr().out)
    assert summary["errors"] == 1 and summary["labels"] == {"REFUSED": 2}
