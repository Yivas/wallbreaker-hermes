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
    assert payload["items"] == 2 and payload["rounds"] == 3
    assert payload["attacker"] == "fixture/brain"
    assert payload["token"]


def test_refuses_without_an_approved_token(wired, capsys):
    assert hunt.run_hunt_cli(_args()) == 2
    assert "Refusing to run" in capsys.readouterr().err

    assert hunt.run_hunt_cli(_args(authorized=True, confirm="wrong")) == 2
    assert "Refusing to run" in capsys.readouterr().err


def test_plan_token_changes_with_the_limits(wired):
    plan_a = hunt.plan_hunt(_args(), _config(None) if False else wired)
    plan_b = hunt.plan_hunt(_args(rounds=9), wired)
    assert plan_a.token() != plan_b.token()


def test_results_have_no_bodies_by_default(wired, tmp_path, monkeypatch, capsys):
    behaviors = [
        {"id": "item-1", "category": "alpha", "behavior": "Synthetic one"},
        {"id": "item-2", "category": "beta", "behavior": "Synthetic two"},
    ]
    monkeypatch.setattr(hunt, "_load_behaviors", lambda plan: behaviors)

    class FakeAttacker:
        async def aclose(self):
            return None

    async def fake_run(provider, registry, messages, **kwargs):
        registry.ctx.record("payload", "response body", "COMPLIED", "reason", None)
        return type("Result", (), {"status": "finished"})()

    monkeypatch.setattr("wallbreaker.providers.factory.build_provider", lambda endpoint, timeout=None: FakeAttacker())
    monkeypatch.setattr("wallbreaker.agent.loop.run_autonomous", fake_run)

    output = tmp_path / "hunt.jsonl"
    args = _args(
        output=str(output),
        authorized=True,
        confirm=hunt.plan_hunt(_args(output=str(output)), wired).token(),
    )
    assert hunt.run_hunt_cli(args) == 0

    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [line["index"] for line in lines] == [1, 2]
    assert lines[0]["verdicts"][0]["label"] == "COMPLIED"
    assert "objective" not in lines[0] and "response" not in lines[0]
    summary = json.loads(capsys.readouterr().out)
    assert summary["items"] == 2 and set(summary["by_category"]) == {"alpha", "beta"}


def test_include_bodies_is_explicit_and_warns(wired, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        hunt,
        "_load_behaviors",
        lambda plan: [{"id": "item-1", "category": "alpha", "behavior": "Synthetic one"}],
    )

    class FakeAttacker:
        async def aclose(self):
            return None

    async def fake_run(provider, registry, messages, **kwargs):
        registry.ctx.record("payload", "response body", "REFUSED", "reason", None)
        return type("Result", (), {"status": "finished"})()

    monkeypatch.setattr("wallbreaker.providers.factory.build_provider", lambda endpoint, timeout=None: FakeAttacker())
    monkeypatch.setattr("wallbreaker.agent.loop.run_autonomous", fake_run)

    output = tmp_path / "bodies.jsonl"
    base = _args(output=str(output), include_bodies=True)
    args = _args(
        output=str(output),
        include_bodies=True,
        authorized=True,
        confirm=hunt.plan_hunt(base, wired).token(),
    )
    assert hunt.run_hunt_cli(args) == 0
    line = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    assert line["objective"] == "Synthetic one"
    assert line["response"] == "response body"
    assert "sensitive" in capsys.readouterr().err
