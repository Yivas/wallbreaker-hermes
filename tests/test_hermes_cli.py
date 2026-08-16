import asyncio
import json
import subprocess
import sys

import pytest

import wallbreaker.hermes_campaign as campaign
import wallbreaker.hermes_cli as hermes_cli
from wallbreaker.cli import build_sub_parser, main
from wallbreaker.config import Config, Endpoint


@pytest.fixture(autouse=True)
def _evidence_key(monkeypatch):
    monkeypatch.setenv(
        "WALLBREAKER_HERMES_EVIDENCE_KEY",
        "fixture-evidence-key-with-at-least-thirty-two-bytes",
    )


def _config():
    attacker = Endpoint("brain", "openai", "https://fixture.invalid", "fixture/brain")
    target = Endpoint("target", "hermes-lab", "", "fixture/target")
    judge = Endpoint("judge", "openai", "https://fixture.invalid", "fixture/judge")
    return Config(
        default_profile="brain",
        profiles={"brain": attacker},
        target=target,
        judge=judge,
    )


def _plan(token=None):
    salt = "a" * 64
    return {
        "schema": "wallbreaker.hermes-campaign-plan/v2",
        "versions": {
            "wallbreaker": "0.2.1",
            "hermes_release": "v2026.8.13",
            "hermes_agent": "0.20.1",
            "hermes_commit": "f" * 40,
        },
        "fingerprint_salt": salt,
        "suite_fingerprint": "1" * 64,
        "config_fingerprint": "2" * 64,
        "output_fingerprint": "3" * 64,
        "resume_checkpoint_fingerprint": None,
        "resume": False,
        "case_count": 3,
        "repetition_count": 9,
        "limits": {
            "repetitions": 3,
            "max_rounds": 12,
            "max_fires": 12,
            "attacker_max_tokens": 8192,
            "target_max_tokens": 1024,
            "timeout": 90.0,
        },
        "maximum_network_requests": 324,
        "maximum_hermes_processes": 216,
        "confirmation": token or f"hmac-sha256:{salt}:" + "b" * 64,
    }


def _events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


@pytest.mark.parametrize("action", ["run", "review", "verify"])
def test_parser_recognizes_hermes_actions(action):
    argv = ["hermes", action]
    if action == "run":
        argv += ["suite.yaml", "--output", "run.json", "--dry-run"]
    else:
        argv += ["run.json"]
    args = build_sub_parser().parse_args(argv)
    assert args.command == "hermes"
    assert args.hermes_action == action


def test_module_entrypoint_exposes_hermes_help():
    completed = subprocess.run(
        [sys.executable, "-m", "wallbreaker", "hermes", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "{run,review,verify}" in completed.stdout


def test_real_dry_run_pipeline_is_offline(tmp_path, monkeypatch, capsys):
    suite = tmp_path / "suite.yaml"
    suite.write_text(
        """schema: wallbreaker.hermes-campaign-suite/v1
id: synthetic-cli
version: 1
cases:
  - id: allow
    split: discovery
    objective: Synthetic allow objective
    prompt: Synthetic allow prompt
    expected_behavior: allow
    expected_state: unchanged
  - id: refuse
    split: qualification
    objective: Synthetic refuse objective
    prompt: Synthetic refuse prompt
    expected_behavior: refuse
    expected_state: unchanged
  - id: context
    split: holdout
    objective: Synthetic context objective
    prompt: Synthetic context prompt
    expected_behavior: context_dependent
    expected_state: manual
""",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "wh-hermes-fixture/v1",
                "mode": "clean",
                "provider": "fixture-provider",
                "model": "fixture/target",
                "files": [],
                "expected_tool_count": 0,
            }
        ),
        encoding="utf-8",
    )
    config = tmp_path / "config.toml"
    config.write_text(
        f'''default_profile = "brain"

[profiles.brain]
protocol = "openai"
base_url = "https://fixture.invalid"
model = "fixture/brain"
api_key = "fixture-key"

[judge]
protocol = "openai"
base_url = "https://fixture.invalid"
model = "fixture/judge"
api_key = "fixture-key"

[target]
protocol = "hermes-lab"
model = "fixture/target"
api_key_env = "FIXTURE_TARGET_KEY"
hermes_provider = "fixture-provider"
hermes_runtime = "{tmp_path.as_posix()}/runtime"
hermes_python = "{tmp_path.as_posix()}/runtime/python"
hermes_manifest = "{manifest.as_posix()}"
''',
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setenv("FIXTURE_TARGET_KEY", "fixture-key")
    monkeypatch.setattr(campaign, "validate_hermes_runtime", lambda endpoint: None)
    monkeypatch.setattr(campaign, "build_provider", lambda endpoint: calls.append(endpoint))

    code = main(
        [
            "hermes",
            "run",
            str(suite),
            "--config",
            str(config),
            "--output",
            str(tmp_path / "report.json"),
            "--dry-run",
        ]
    )

    events = _events(capsys)
    assert code == 0
    assert calls == []
    assert events[0]["event"] == "plan.validated"
    assert events[0]["data"]["maximum_network_requests"] == 324


def test_missing_authorization_fails_before_config_load(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(hermes_cli, "load_config", lambda path: calls.append(path))

    code = main(["hermes", "run", "suite.yaml", "--output", "run.json"])

    assert code == 3
    assert calls == []
    assert _events(capsys)[-1]["data"]["status"] == "authorization_required"


def test_dry_run_has_no_runner_or_private_output(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(hermes_cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(hermes_cli, "load_config", lambda path: _config())
    monkeypatch.setattr(hermes_cli, "load_suite", lambda path: object())
    monkeypatch.setattr(hermes_cli, "build_campaign_plan", lambda *args, **kwargs: _plan())
    monkeypatch.setattr(hermes_cli, "run_campaign", lambda *args, **kwargs: calls.append(args))

    code = main(
        [
            "hermes",
            "run",
            "synthetic-suite.yaml",
            "--output",
            "synthetic-run.json",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    events = [json.loads(line) for line in output.splitlines()]
    assert code == 0
    assert calls == []
    assert [event["event"] for event in events] == ["plan.validated", "result"]
    for private in ("Synthetic private prompt", "fixture.invalid", "SECRET_VALUE"):
        assert private not in output


def test_confirmation_mismatch_fails_before_runner(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(hermes_cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(hermes_cli, "load_config", lambda path: _config())
    monkeypatch.setattr(hermes_cli, "load_suite", lambda path: object())
    monkeypatch.setattr(hermes_cli, "build_campaign_plan", lambda *args, **kwargs: _plan())
    monkeypatch.setattr(hermes_cli, "run_campaign", lambda *args, **kwargs: calls.append(args))

    code = main(
        [
            "hermes",
            "run",
            "suite.yaml",
            "--output",
            "run.json",
            "--authorized",
            "--confirm",
            "hmac-sha256:" + "c" * 64 + ":" + "d" * 64,
        ]
    )

    assert code == 3
    assert calls == []
    assert _events(capsys)[-1]["data"]["status"] == "confirmation_mismatch"


def test_confirmed_run_uses_existing_runner_and_emits_progress(monkeypatch, capsys):
    calls = []
    report = {"status": "complete", "repetitions": []}
    monkeypatch.setattr(hermes_cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(hermes_cli, "load_config", lambda path: _config())
    monkeypatch.setattr(hermes_cli, "load_suite", lambda path: object())
    monkeypatch.setattr(hermes_cli, "build_campaign_plan", lambda *args, **kwargs: _plan())
    monkeypatch.setattr(hermes_cli, "_result_code", lambda value: 0)
    monkeypatch.setattr(hermes_cli, "_summary", lambda value: {"status": "complete"})

    async def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        kwargs["event_sink"]("repetition.started", {"attempt_id": "1" * 64})
        return report

    monkeypatch.setattr(hermes_cli, "run_campaign", fake_run)

    code = main(
        [
            "hermes",
            "run",
            "suite.yaml",
            "--output",
            "run.json",
            "--max-fires",
            "7",
            "--authorized",
            "--confirm",
            _plan()["confirmation"],
        ]
    )

    events = _events(capsys)
    assert code == 0
    assert len(calls) == 1
    assert calls[0][0][3].max_fires == 7
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert "repetition.started" in [event["event"] for event in events]
    assert events[-1]["event"] == "result"


def test_review_lists_pending_without_config_or_network(monkeypatch, capsys):
    report = {"status": "partial"}
    monkeypatch.setattr(hermes_cli, "load_campaign_report", lambda path: report)
    monkeypatch.setattr(
        hermes_cli,
        "_summary",
        lambda value: {"status": "partial", "pending_review_ids": ["1" * 64]},
    )

    code = main(["hermes", "review", "run.json"])

    assert code == 2
    events = _events(capsys)
    assert events[0]["event"] == "review.pending"
    assert events[-1]["data"]["pending_review_ids"] == ["1" * 64]


def test_duplicate_review_decisions_fail_before_mutation(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(hermes_cli, "load_campaign_report", lambda path: {"status": "partial"})
    monkeypatch.setattr(hermes_cli, "apply_reviews", lambda *args: calls.append(args))
    attempt = "1" * 64

    code = main(
        [
            "hermes",
            "review",
            "run.json",
            "--set",
            f"{attempt}=pass",
            "--set",
            f"{attempt}=finding",
        ]
    )

    assert code == 1
    assert calls == []
    assert _events(capsys)[-1]["data"]["status"] == "error"


def test_verify_is_offline_and_returns_action_required(monkeypatch, capsys):
    report = {"status": "partial"}
    monkeypatch.setattr(hermes_cli, "load_campaign_report", lambda path: report)
    monkeypatch.setattr(hermes_cli, "campaign_verification_issues", lambda value: ("review_pending",))
    monkeypatch.setattr(
        hermes_cli,
        "_summary",
        lambda value: {"status": "partial", "pending_review_ids": ["1" * 64]},
    )

    code = main(["hermes", "verify", "run.json"])

    assert code == 2
    events = _events(capsys)
    assert events[0]["data"]["issues"] == ["review_pending"]
    assert events[-1]["data"]["status"] == "incomplete"


@pytest.mark.parametrize("error", [KeyboardInterrupt(), asyncio.CancelledError()])
def test_cancellation_returns_130(monkeypatch, capsys, error):
    monkeypatch.setattr(hermes_cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(hermes_cli, "load_config", lambda path: _config())
    monkeypatch.setattr(hermes_cli, "load_suite", lambda path: object())
    monkeypatch.setattr(hermes_cli, "build_campaign_plan", lambda *args, **kwargs: _plan())

    def interrupt(coroutine):
        coroutine.close()
        raise error

    monkeypatch.setattr(hermes_cli.asyncio, "run", interrupt)

    code = main(
        [
            "hermes",
            "run",
            "suite.yaml",
            "--output",
            "run.json",
            "--authorized",
            "--confirm",
            _plan()["confirmation"],
        ]
    )

    assert code == 130
    assert _events(capsys)[-1]["data"]["status"] == "cancelled"


def test_invalid_limit_is_argparse_error_before_config(monkeypatch):
    calls = []
    monkeypatch.setattr(hermes_cli, "load_config", lambda path: calls.append(path))
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "hermes",
                "run",
                "suite.yaml",
                "--output",
                "run.json",
                "--max-fires",
                "21",
                "--dry-run",
            ]
        )
    assert exc.value.code == 2
    assert calls == []
