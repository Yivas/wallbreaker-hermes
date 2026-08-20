import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

import wallbreaker.hermes_campaign as campaign
from wallbreaker import __version__
from wallbreaker.agent.messages import StopEvent, ToolUseEvent
from wallbreaker.hermes_campaign import (
    Assessment,
    AttemptStatus,
    CampaignError,
    CampaignSettings,
    _config_fingerprint,
    _fingerprint,
    _initial_report,
    _new_attempt,
    _new_review_evidence,
    _private_fingerprint,
    _refresh,
    _register_target,
    _run_repetition,
    _write_private_json,
    build_campaign_plan,
    campaign_evidence_path,
    campaign_verification_issues,
    load_campaign_report,
    resume_campaign,
    run_campaign,
    validate_campaign_report,
)
from wallbreaker.config import Config, Endpoint
from wallbreaker.hermes_lab import (
    HERMES_MANIFEST_SCHEMA,
    CleanupReceipt,
    HermesLabReplica,
    fingerprint_manifest_context,
)
from wallbreaker.providers.base import ProviderError
from wallbreaker.tools.registry import ToolContext, ToolRegistry


@pytest.fixture(autouse=True)
def _evidence_key(monkeypatch):
    monkeypatch.setenv(
        "WALLBREAKER_HERMES_EVIDENCE_KEY",
        "fixture-evidence-key-with-at-least-thirty-two-bytes",
    )


def _suite(path):
    path.write_text(
        f"""schema: {campaign.SUITE_SCHEMA}
id: synthetic-suite
version: 1
cases:
  - id: allow-case
    split: discovery
    objective: Synthetic allow objective
    prompt: Synthetic allow prompt
    expected_behavior: allow
    expected_state: unchanged
  - id: refuse-case
    split: qualification
    objective: Synthetic refuse objective
    prompt: Synthetic refuse prompt
    expected_behavior: refuse
    expected_state: unchanged
  - id: context-case
    split: holdout
    objective: Synthetic context objective
    prompt: Synthetic context prompt
    expected_behavior: context_dependent
    expected_state: manual
""",
        encoding="utf-8",
    )
    return campaign.load_suite(path)


def _config(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": HERMES_MANIFEST_SCHEMA,
                "mode": "clean",
                "provider": "fixture-provider",
                "model": "fixture/target",
                "files": [],
                "expected_tool_count": 0,
            }
        ),
        encoding="utf-8",
    )
    attacker = Endpoint("brain", "openai", "https://fixture.invalid", "fixture/brain")
    target = Endpoint(
        "target",
        "hermes-lab",
        "",
        "fixture/target",
        hermes_provider="fixture-provider",
        hermes_manifest=str(manifest),
    )
    judge = Endpoint("judge", "openai", "https://fixture.invalid", "fixture/judge")
    return Config(
        default_profile="brain",
        profiles={"brain": attacker},
        target=target,
        judge=judge,
    ), attacker


def _fire():
    return {
        "prompt_fingerprint": "1" * 64,
        "response_fingerprint": "2" * 64,
        "assessment": Assessment.PASS.value,
        "behavior": {
            "expected": "allow",
            "judge_label": "COMPLIED",
            "judge_score": 10,
            "judge_status": "passed",
            "judge_error_type": None,
            "heuristic_label": "COMPLIED",
            "assessment": Assessment.PASS.value,
        },
        "state": {
            "expected": "unchanged",
            "allowed_components": [],
            "changed_components": [],
            "initial_fingerprint": "3" * 64,
            "final_fingerprint": "3" * 64,
            "assessment": Assessment.PASS.value,
        },
        "tools": {"attempt_count": 0, "assessment": Assessment.PASS.value},
        "attestation": {
            "preflight_fingerprint": "4" * 64,
            "run_fingerprint": "5" * 64,
        },
        "cleanup": {
            "outcome": "success",
            "root_removed": True,
            "process_reaped": True,
            "source_unchanged": True,
        },
        "response_transform": {"status": "not_requested", "error_type": None},
    }


def _target_result():
    return SimpleNamespace(
        text="Synthetic response",
        evidence=SimpleNamespace(
            changed_components=(),
            tool_attempt_count=0,
            preflight_fingerprint="1" * 64,
            run_fingerprint="2" * 64,
            initial_state=(("SOUL.md", "3" * 64),),
            final_state=(("SOUL.md", "3" * 64),),
        ),
        cleanup=SimpleNamespace(
            outcome="success",
            root_removed=True,
            process_reaped=True,
            source_unchanged=True,
        ),
    )


def _complete_report(tmp_path):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    settings = CampaignSettings(repetitions=1)
    report = _initial_report(
        suite,
        _config_fingerprint(config, attacker, config.judge, settings),
        settings,
    )
    for repetition in report["repetitions"]:
        attempt = repetition["attempts"][-1]
        attempt["status"] = AttemptStatus.COMPLETED.value
        attempt["autonomous_status"] = "finished"
        attempt["assessment"] = Assessment.PASS.value
        attempt["automatic_assessment"] = Assessment.PASS.value
        attempt["invocations"] = [
            {"status": "success", "cleanup": _fire()["cleanup"]}
        ]
        attempt["fires"] = [_fire()]
    _refresh(report)
    return report


def _write_report_with_evidence(path, report):
    evidence = _new_review_evidence(report)
    for repetition in report["repetitions"]:
        for attempt in repetition["attempts"]:
            for fire_index, fire in enumerate(attempt["fires"]):
                prompt = f"Synthetic prompt {attempt['id']} {fire_index}"
                response = f"Synthetic response {attempt['id']} {fire_index}"
                fire["prompt_fingerprint"] = _private_fingerprint(
                    "prompt", prompt, report["fingerprint_salt"]
                )
                fire["response_fingerprint"] = _private_fingerprint(
                    "response", response, report["fingerprint_salt"]
                )
                evidence["fires"].append(
                    {
                        "attempt_id": attempt["id"],
                        "fire_index": fire_index,
                        "objective": "Synthetic objective",
                        "prompt": prompt,
                        "response": response,
                        "objective_fingerprint": _private_fingerprint(
                            "objective", "Synthetic objective", report["fingerprint_salt"]
                        ),
                        "prompt_fingerprint": fire["prompt_fingerprint"],
                        "response_fingerprint": fire["response_fingerprint"],
                    }
                )
    path.write_text(json.dumps(report), encoding="utf-8")
    _write_private_json(campaign_evidence_path(path), evidence)


def test_campaign_settings_preserve_existing_positional_order():
    settings = CampaignSettings(3, 12, 8192, 1024, 90)
    assert settings.attacker_max_tokens == 8192
    assert settings.target_max_tokens == 1024
    assert settings.timeout == 90
    assert settings.max_fires == 12


def test_plan_is_deterministic_and_binds_limits_output_and_resume(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    output = tmp_path / "report.json"
    monkeypatch.setattr(campaign, "_require_endpoint_credentials", lambda *args: None)
    monkeypatch.setattr(campaign, "validate_hermes_runtime", lambda endpoint: None)

    salt = "a" * 64
    first = build_campaign_plan(
        suite,
        config,
        output,
        attacker_endpoint=attacker,
        fingerprint_salt=salt,
    )
    second = build_campaign_plan(
        suite,
        config,
        output,
        attacker_endpoint=attacker,
        fingerprint_salt=salt,
    )

    assert first == second
    assert first["schema"] == "wallbreaker.hermes-campaign-plan/v2"
    assert first["versions"]["wallbreaker"] == __version__
    assert first["fingerprint_salt"] == salt
    assert first["maximum_network_requests"] == 324
    assert first["maximum_hermes_processes"] == 216
    assert first["maximum_private_evidence_bytes"] < 64 * 1024 * 1024
    assert first["confirmation"].startswith(f"hmac-sha256:{salt}:")
    changed = build_campaign_plan(
        suite,
        config,
        output,
        CampaignSettings(max_fires=11),
        attacker,
        fingerprint_salt=salt,
    )
    assert changed["confirmation"] != first["confirmation"]


def test_resume_plan_binds_validated_checkpoint(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    settings = CampaignSettings(repetitions=1)
    report = _complete_report(tmp_path)
    output = tmp_path / "report.json"
    _write_report_with_evidence(output, report)
    monkeypatch.setattr(campaign, "_require_endpoint_credentials", lambda *args: None)
    monkeypatch.setattr(campaign, "validate_hermes_runtime", lambda endpoint: None)

    first = build_campaign_plan(
        suite,
        config,
        output,
        settings,
        attacker,
        resume=True,
    )
    attempt = report["repetitions"][0]["attempts"][-1]
    attempt["review"] = Assessment.FINDING.value
    attempt["assessment"] = Assessment.FINDING.value
    _refresh(report)
    output.write_text(json.dumps(report), encoding="utf-8")
    second = build_campaign_plan(
        suite,
        config,
        output,
        settings,
        attacker,
        resume=True,
    )

    assert first["resume_checkpoint_fingerprint"] != second[
        "resume_checkpoint_fingerprint"
    ]
    assert first["confirmation"] != second["confirmation"]


def test_plan_rejects_missing_or_incompatible_hermes_before_provider(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    calls = []

    def missing_runtime(endpoint):
        raise ProviderError("Hermes runtime is missing.")

    monkeypatch.setattr(campaign, "_require_endpoint_credentials", lambda *args: None)
    monkeypatch.setattr(campaign, "validate_hermes_runtime", missing_runtime)
    monkeypatch.setattr(campaign, "build_provider", lambda endpoint: calls.append(endpoint))

    with pytest.raises(ProviderError, match="missing"):
        build_campaign_plan(suite, config, tmp_path / "report.json", attacker_endpoint=attacker)
    assert calls == []


@pytest.mark.asyncio
async def test_authorized_plan_rejects_config_drift_before_provider(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    output = tmp_path / "report.json"
    calls = []
    monkeypatch.setattr(campaign, "_require_endpoint_credentials", lambda *args: None)
    monkeypatch.setattr(campaign, "validate_hermes_runtime", lambda endpoint: None)
    monkeypatch.setattr(campaign, "build_provider", lambda endpoint: calls.append(endpoint))
    plan = build_campaign_plan(suite, config, output, attacker_endpoint=attacker)
    attacker.model = "fixture/changed"

    with pytest.raises(CampaignError, match="changed after authorization"):
        await run_campaign(
            suite,
            config,
            output,
            attacker_endpoint=attacker,
            expected_plan=plan,
        )
    assert calls == []
    assert not output.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["attacker", "judge", "target"])
async def test_authorized_plan_binds_effective_credentials(
    tmp_path, monkeypatch, changed
):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    output = tmp_path / "report.json"
    attacker.api_key = "fixture-attacker-a"
    config.judge.api_key = "fixture-judge-a"
    config.target.api_key_env = "FIXTURE_TARGET_KEY"
    monkeypatch.setenv("FIXTURE_TARGET_KEY", "fixture-target-a")
    monkeypatch.setattr(campaign, "validate_hermes_runtime", lambda endpoint: None)
    calls = []
    monkeypatch.setattr(campaign, "build_provider", lambda endpoint: calls.append(endpoint))
    plan = build_campaign_plan(suite, config, output, attacker_endpoint=attacker)

    if changed == "attacker":
        attacker.api_key = "fixture-attacker-b"
    elif changed == "judge":
        config.judge.api_key = "fixture-judge-b"
    else:
        monkeypatch.setenv("FIXTURE_TARGET_KEY", "fixture-target-b")

    with pytest.raises(CampaignError, match="changed after authorization"):
        await run_campaign(
            suite,
            config,
            output,
            attacker_endpoint=attacker,
            expected_plan=plan,
        )
    assert calls == []


@pytest.mark.asyncio
async def test_run_persists_the_authorized_frozen_snapshot(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    output = tmp_path / "report.json"
    attacker.api_key_env = "FIXTURE_ATTACKER_KEY"
    prompt_file = tmp_path / "attacker-prompt.txt"
    prompt_file.write_text("authorized prompt", encoding="utf-8")
    attacker.system_prompt_file = str(prompt_file)
    config.judge.api_key = "fixture-judge"
    config.target.api_key = "fixture-target"
    monkeypatch.setenv("FIXTURE_ATTACKER_KEY", "fixture-attacker-a")
    monkeypatch.setattr(campaign, "validate_hermes_runtime", lambda endpoint: None)
    settings = CampaignSettings(repetitions=1)
    plan = build_campaign_plan(
        suite, config, output, settings, attacker_endpoint=attacker
    )

    async def fake_run(*args, **kwargs):
        assert args[2].system_prompt == "authorized prompt"
        assert args[2].system_prompt_file == ""
        fire = _fire()
        args[7]()
        args[8](CleanupReceipt("success", True, True, True))
        args[4](fire)
        return "finished", Assessment.PASS, [fire]

    def mutate_original(event, payload):
        if event == "campaign.started":
            monkeypatch.setenv("FIXTURE_ATTACKER_KEY", "fixture-attacker-b")
            attacker.model = "changed-after-snapshot"
            prompt_file.write_text("changed prompt", encoding="utf-8")

    monkeypatch.setattr(campaign, "_run_repetition", fake_run)
    report = await run_campaign(
        suite,
        config,
        output,
        settings,
        attacker,
        event_sink=mutate_original,
        expected_plan=plan,
    )

    validate_campaign_report(report)
    assert report["config_fingerprint"] == plan["config_fingerprint"]


@pytest.mark.asyncio
async def test_run_repetition_uses_frozen_operator_prompt(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    prompt_file = tmp_path / "attacker-prompt.txt"
    prompt_file.write_text("authorized operator", encoding="utf-8")
    attacker.system_prompt_file = str(prompt_file)
    frozen = campaign._freeze_endpoint(attacker)
    assert frozen is not None
    prompt_file.write_text("changed operator", encoding="utf-8")
    systems = []

    class FakeAttacker:
        async def aclose(self):
            return None

    async def fake_autonomous(*args, **kwargs):
        systems.append(kwargs["system"])
        return SimpleNamespace(status="finished")

    def fake_register(registry, case, settings, fires, judge, *args):
        fires.append(_fire())

    monkeypatch.setattr(campaign, "build_provider", lambda endpoint: FakeAttacker())
    monkeypatch.setattr(campaign, "run_autonomous", fake_autonomous)
    monkeypatch.setattr(campaign, "_register_target", fake_register)

    await _run_repetition(
        suite.cases[0],
        config,
        frozen,
        CampaignSettings(repetitions=1),
        attacker_system=campaign._attacker_system(frozen),
    )

    assert systems == [f"authorized operator\n\n{campaign._CAMPAIGN_SYSTEM}"]


def test_context_fingerprint_hashes_the_parsed_manifest_bytes(tmp_path, monkeypatch):
    config, _ = _config(tmp_path)
    manifest = {
        "schema": HERMES_MANIFEST_SCHEMA,
        "mode": "clean",
        "provider": config.target.hermes_provider,
        "model": config.target.model,
        "files": [],
        "expected_tool_count": 0,
    }
    parsed_bytes = b"authorized-manifest-snapshot"

    def snapshot(replica):
        replica.manifest_path.write_bytes(b"changed-after-parse")
        return manifest, parsed_bytes

    monkeypatch.setattr(HermesLabReplica, "_load_manifest_snapshot", snapshot)

    assert fingerprint_manifest_context(config.target) == hashlib.sha256(
        parsed_bytes
    ).hexdigest()


@pytest.mark.asyncio
async def test_replica_rejects_context_changed_after_authorization(tmp_path, monkeypatch):
    config, _ = _config(tmp_path)
    config.target.hermes_context_fingerprint = "0" * 64
    replica = HermesLabReplica(config.target, 15)
    monkeypatch.setattr(replica, "_validate_runtime", lambda: None)
    monkeypatch.setattr(replica, "_secure_root", lambda: None)
    monkeypatch.setattr(replica, "_write_runtime_files", lambda max_tokens: None)
    monkeypatch.setattr(replica, "_copy_manifest_files", lambda files: None)

    with pytest.raises(ProviderError, match="changed after authorization"):
        replica.prepare(1024)
    await replica.close()


def test_plan_rejects_excessive_private_evidence_without_provider(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    monkeypatch.setattr(campaign, "_require_endpoint_credentials", lambda *args: None)
    monkeypatch.setattr(campaign, "validate_hermes_runtime", lambda endpoint: None)

    with pytest.raises(CampaignError, match="private evidence budget"):
        build_campaign_plan(
            suite,
            config,
            tmp_path / "report.json",
            CampaignSettings(repetitions=10, max_rounds=1, max_fires=6),
            attacker,
        )


def test_plan_rejects_excessive_known_requests_without_provider(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    monkeypatch.setattr(campaign, "_require_endpoint_credentials", lambda *args: None)
    monkeypatch.setattr(campaign, "validate_hermes_runtime", lambda endpoint: None)
    calls = []
    monkeypatch.setattr(campaign, "build_provider", lambda endpoint: calls.append(endpoint))

    with pytest.raises(CampaignError, match="1000"):
        build_campaign_plan(
            suite,
            config,
            tmp_path / "report.json",
            CampaignSettings(repetitions=10, max_rounds=50, max_fires=20),
            attacker,
        )
    assert calls == []


@pytest.mark.asyncio
async def test_campaign_uses_one_attacker_request_per_round(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    observed = []

    class FakeAttacker:
        async def aclose(self):
            return None

    async def fake_run(*args, **kwargs):
        observed.append(kwargs)
        return SimpleNamespace(status="finished")

    monkeypatch.setattr(campaign, "build_provider", lambda endpoint: FakeAttacker())
    monkeypatch.setattr(campaign, "run_autonomous", fake_run)

    with pytest.raises(CampaignError, match="no target evidence"):
        await _run_repetition(
            suite.cases[0], config, attacker, CampaignSettings(repetitions=1)
        )
    assert observed[0]["max_iters"] == 1


@pytest.mark.asyncio
async def test_plan_drift_tool_error_is_fatal_to_repetition(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)

    class FakeAttacker:
        def __init__(self):
            self.calls = 0

        async def stream(self, *args, **kwargs):
            if self.calls == 0:
                self.calls += 1
                yield ToolUseEvent("target", "query_target", {"prompt": "Synthetic"})
                yield StopEvent("tool_use")
                return
            yield ToolUseEvent("finish", "finish", {"summary": "done"})
            yield StopEvent("tool_use")

        async def aclose(self):
            return None

    def changed_plan():
        raise CampaignError("Campaign inputs changed after authorization.")

    monkeypatch.setattr(campaign, "build_provider", lambda endpoint: FakeAttacker())

    with pytest.raises(CampaignError, match="changed after authorization"):
        await _run_repetition(
            suite.cases[0],
            config,
            attacker,
            CampaignSettings(repetitions=1),
            before_fire=changed_plan,
        )


@pytest.mark.asyncio
async def test_fire_limit_stops_before_provider_construction(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, _ = _config(tmp_path)
    fires = []
    registry = ToolRegistry(ToolContext(config=config, vault_enabled=False))
    reached = []
    calls = []

    class FakeTarget:
        async def fire(self, *args, **kwargs):
            return _target_result()
    _register_target(
        registry,
        suite.cases[0],
        CampaignSettings(repetitions=1, max_fires=1),
        fires,
        None,
        on_limit=lambda: reached.append(True),
    )
    monkeypatch.setattr(
        campaign,
        "build_provider",
        lambda endpoint: calls.append(endpoint) or FakeTarget(),
    )
    await registry.execute("query_target", {"prompt": "Synthetic prompt"})
    result = await registry.execute("query_target", {"prompt": "Synthetic prompt"})

    assert result.content == "Error: campaign target fire limit reached"
    assert reached == [True]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_failed_target_invocation_consumes_fire_limit(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, _ = _config(tmp_path)
    registry = ToolRegistry(ToolContext(config=config, vault_enabled=False))
    calls = []

    class FailingTarget:
        async def fire(self, *args, **kwargs):
            raise ProviderError("Synthetic target failure")

    monkeypatch.setattr(
        campaign,
        "build_provider",
        lambda endpoint, timeout=None: calls.append(endpoint) or FailingTarget(),
    )
    _register_target(
        registry,
        suite.cases[0],
        CampaignSettings(repetitions=1, max_fires=1),
        [],
        config.judge,
    )

    first = await registry.execute("query_target", {"prompt": "Synthetic prompt"})
    second = await registry.execute("query_target", {"prompt": "Synthetic prompt"})

    assert first.is_error is True
    assert second.content == "Error: campaign target fire limit reached"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_second_drift_check_closes_unstarted_invocation(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, _ = _config(tmp_path)
    registry = ToolRegistry(ToolContext(config=config, vault_enabled=False))
    checks = 0
    invocations = []
    providers = []

    def check_plan():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise CampaignError("Campaign inputs changed after authorization.")

    def start():
        invocations.append({"status": "running", "cleanup": None})

    def close(receipt):
        invocations[-1] = {
            "status": receipt.outcome,
            "cleanup": campaign._cleanup_data(receipt),
        }

    monkeypatch.setattr(campaign, "build_provider", lambda endpoint: providers.append(endpoint))
    _register_target(
        registry,
        suite.cases[0],
        CampaignSettings(repetitions=1),
        [],
        None,
        on_invocation_start=start,
        on_invocation_unverified=close,
        before_fire=check_plan,
    )

    result = await registry.execute("query_target", {"prompt": "Synthetic prompt"})
    assert result.is_error
    assert providers == []
    assert invocations == [
        {
            "status": "not_started",
            "cleanup": {
                "outcome": "not_started",
                "root_removed": True,
                "process_reaped": True,
                "source_unchanged": True,
            },
        }
    ]


@pytest.mark.asyncio
async def test_cancelled_target_invocation_returns_verified_cleanup(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, _ = _config(tmp_path)
    registry = ToolRegistry(ToolContext(config=config, vault_enabled=False))
    receipt = CleanupReceipt("cancelled", True, True, True)
    started = []
    failed = []

    class CancelledTarget:
        last_cleanup = receipt

        async def fire(self, *args, **kwargs):
            raise asyncio.CancelledError

    monkeypatch.setattr(campaign, "build_provider", lambda endpoint: CancelledTarget())
    _register_target(
        registry,
        suite.cases[0],
        CampaignSettings(repetitions=1),
        [],
        None,
        on_invocation_start=lambda: started.append(True),
        on_invocation_unverified=lambda value: failed.append(value),
    )

    with pytest.raises(asyncio.CancelledError):
        await registry.execute("query_target", {"prompt": "Synthetic prompt"})
    assert started == [True]
    assert failed == [receipt]


@pytest.mark.asyncio
async def test_campaign_timeout_overrides_target_endpoint_timeout(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, _ = _config(tmp_path)
    config.target.timeout = 599
    registry = ToolRegistry(ToolContext(config=config, vault_enabled=False))
    observed = []

    class FakeTarget:
        async def fire(self, *args, **kwargs):
            return _target_result()

    def fake_build(endpoint, timeout=None):
        observed.append(endpoint.timeout)
        return FakeTarget()

    async def fake_judge(*args, **kwargs):
        return {"label": "PARTIAL", "score": 5, "reason": "fixture"}

    monkeypatch.setattr(campaign, "build_provider", fake_build)
    monkeypatch.setattr(campaign, "judge_reply", fake_judge)
    _register_target(
        registry,
        suite.cases[0],
        CampaignSettings(repetitions=1, timeout=15),
        [],
        None,
    )

    await registry.execute("query_target", {"prompt": "Synthetic prompt"})
    assert observed == [15]


def test_report_validation_and_strict_cleanup_gate(tmp_path):
    report = _complete_report(tmp_path)
    assert validate_campaign_report(report) is report
    assert campaign_verification_issues(report) == ()

    incomplete = copy.deepcopy(report)
    incomplete["repetitions"][0]["attempts"][-1]["fires"][0]["cleanup"][
        "root_removed"
    ] = False
    assert campaign_verification_issues(incomplete) == ("cleanup_unverified",)

    injected = copy.deepcopy(report)
    injected["prompt"] = "Synthetic private prompt"
    with pytest.raises(CampaignError, match="invalid"):
        validate_campaign_report(injected)

    wrong_version = copy.deepcopy(report)
    wrong_version["versions"]["wallbreaker"] = "0.1.0"
    with pytest.raises(CampaignError, match="invalid"):
        validate_campaign_report(wrong_version)


@pytest.mark.asyncio
async def test_resume_compacts_replaced_attempt_private_bodies_before_new_run(
    tmp_path, monkeypatch
):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    report = _complete_report(tmp_path)
    old_attempt = report["repetitions"][0]["attempts"][-1]
    old_attempt["status"] = AttemptStatus.FAILED.value
    old_attempt["assessment"] = Assessment.MANUAL_REQUIRED.value
    old_attempt["automatic_assessment"] = None
    old_attempt["review"] = None
    old_attempt["error_type"] = "SyntheticError"
    _refresh(report)
    output = tmp_path / "retry-report.json"
    _write_report_with_evidence(output, report)
    observed = []

    async def inspect_compacted(*args, **kwargs):
        current_report = load_campaign_report(output)
        current_evidence = campaign.load_campaign_evidence(output, current_report)
        observed.extend(record["attempt_id"] for record in current_evidence["fires"])
        raise RuntimeError("synthetic stop after compaction")

    monkeypatch.setattr(campaign, "_run_repetition", inspect_compacted)
    await resume_campaign(
        suite,
        config,
        output,
        CampaignSettings(repetitions=1),
        attacker,
    )
    assert old_attempt["id"] not in observed


def test_legacy_v2_report_with_fires_has_explicit_resume_error(tmp_path, monkeypatch):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    report = _complete_report(tmp_path)
    output = tmp_path / "legacy-report.json"
    output.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(campaign, "_require_endpoint_credentials", lambda *args: None)
    monkeypatch.setattr(campaign, "validate_hermes_runtime", lambda endpoint: None)

    with pytest.raises(CampaignError, match="predates private review evidence"):
        build_campaign_plan(
            suite,
            config,
            output,
            CampaignSettings(repetitions=1),
            attacker,
            resume=True,
        )


@pytest.mark.asyncio
async def test_resume_rejects_reordered_suite_topology(tmp_path):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    settings = CampaignSettings(repetitions=1)
    report = _complete_report(tmp_path)
    report["repetitions"][0], report["repetitions"][1] = (
        report["repetitions"][1],
        report["repetitions"][0],
    )
    output = tmp_path / "report.json"
    _write_report_with_evidence(output, report)

    with pytest.raises(CampaignError, match="identity"):
        await resume_campaign(suite, config, output, settings, attacker)


def test_report_rejects_missing_split_topology(tmp_path):
    report = _complete_report(tmp_path)
    report["repetitions"] = [
        repetition
        for repetition in report["repetitions"]
        if repetition["split"] != "qualification"
    ]
    _refresh(report)

    with pytest.raises(CampaignError, match="invalid"):
        validate_campaign_report(report)


def test_report_rejects_unreviewed_manual_component_evidence(tmp_path):
    report = _complete_report(tmp_path)
    attempt = report["repetitions"][0]["attempts"][-1]
    attempt["fires"][0]["behavior"]["assessment"] = Assessment.MANUAL_REQUIRED.value

    with pytest.raises(CampaignError, match="invalid"):
        validate_campaign_report(report)


def test_report_rejects_error_on_completed_attempt(tmp_path):
    report = _complete_report(tmp_path)
    report["repetitions"][0]["attempts"][-1]["error_type"] = "SyntheticError"

    with pytest.raises(CampaignError, match="invalid"):
        validate_campaign_report(report)


def test_report_rejects_state_fingerprint_contradiction(tmp_path):
    report = _complete_report(tmp_path)
    state = report["repetitions"][0]["attempts"][-1]["fires"][0]["state"]
    state["final_fingerprint"] = "9" * 64

    with pytest.raises(CampaignError, match="invalid"):
        validate_campaign_report(report)


def test_report_rejects_boolean_numeric_fields(tmp_path):
    report = _complete_report(tmp_path)
    report["repetitions"][0]["attempts"][-1]["fires"][0]["behavior"][
        "judge_score"
    ] = True

    with pytest.raises(CampaignError, match="invalid"):
        validate_campaign_report(report)


def test_report_loader_rejects_duplicate_keys_and_nonfinite_numbers(tmp_path):
    report = _complete_report(tmp_path)
    duplicate = json.dumps(report).replace(
        '"schema":', '"schema":"duplicate","schema":', 1
    )
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(duplicate, encoding="utf-8")
    with pytest.raises(CampaignError, match="duplicate"):
        load_campaign_report(duplicate_path)

    report["repetitions"][0]["attempts"][-1]["fires"][0]["behavior"][
        "judge_score"
    ] = float("nan")
    nan_path = tmp_path / "nan.json"
    nan_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(CampaignError, match="non-finite"):
        load_campaign_report(nan_path)


def test_verified_cancelled_invocation_allows_clean_resume_verification(tmp_path):
    report = _complete_report(tmp_path)
    repetition = report["repetitions"][0]
    completed = repetition["attempts"][-1]
    completed["ordinal"] = 1
    completed["id"] = _fingerprint([repetition["id"], 1])
    cancelled = _new_attempt(repetition["id"], 0)
    cancelled["status"] = AttemptStatus.REPLACED.value
    cancelled["assessment"] = Assessment.MANUAL_REQUIRED.value
    cancelled["invocations"] = [
        {
            "status": "cancelled",
            "cleanup": {
                "outcome": "cancelled",
                "root_removed": True,
                "process_reaped": True,
                "source_unchanged": True,
            },
        }
    ]
    repetition["attempts"] = [cancelled, completed]
    _refresh(report)

    validate_campaign_report(report)
    assert campaign_verification_issues(report) == ()


def test_terminal_invocation_without_fire_is_reloadable_but_not_verified(tmp_path):
    report = _complete_report(tmp_path)
    repetition = report["repetitions"][0]
    completed = repetition["attempts"][-1]
    completed["ordinal"] = 1
    completed["id"] = _fingerprint([repetition["id"], 1])
    interrupted = _new_attempt(repetition["id"], 0)
    interrupted["status"] = AttemptStatus.REPLACED.value
    interrupted["assessment"] = Assessment.MANUAL_REQUIRED.value
    interrupted["invocations"] = [
        {
            "status": "success",
            "cleanup": {
                "outcome": "success",
                "root_removed": True,
                "process_reaped": True,
                "source_unchanged": True,
            },
        }
    ]
    repetition["attempts"] = [interrupted, completed]
    _refresh(report)
    path = tmp_path / "interrupted-report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    loaded = load_campaign_report(path)
    assert "target_evidence_pending" in campaign_verification_issues(loaded)


def test_open_target_invocation_prevents_strict_verification(tmp_path):
    report = _complete_report(tmp_path)
    attempt = report["repetitions"][0]["attempts"][-1]
    attempt["invocations"].append({"status": "unverified", "cleanup": None})
    attempt["automatic_assessment"] = Assessment.MANUAL_REQUIRED.value
    attempt["review"] = Assessment.PASS.value

    validate_campaign_report(report)
    assert "target_cleanup_unverified" in campaign_verification_issues(report)


def test_manual_review_cannot_clear_confirmed_finding(tmp_path):
    report = _complete_report(tmp_path)
    attempt = report["repetitions"][0]["attempts"][-1]
    attempt["fires"][0]["state"]["changed_components"] = ["soul"]
    attempt["fires"][0]["state"]["final_fingerprint"] = "9" * 64
    attempt["fires"][0]["state"]["assessment"] = Assessment.FINDING.value
    attempt["fires"][0]["behavior"]["judge_label"] = None
    attempt["fires"][0]["behavior"]["judge_score"] = None
    attempt["fires"][0]["behavior"]["judge_status"] = "failed"
    attempt["fires"][0]["behavior"]["judge_error_type"] = "RuntimeError"
    attempt["fires"][0]["behavior"]["assessment"] = Assessment.MANUAL_REQUIRED.value
    attempt["fires"][0]["assessment"] = Assessment.MANUAL_REQUIRED.value
    attempt["status"] = AttemptStatus.REVIEW_REQUIRED.value
    attempt["assessment"] = Assessment.MANUAL_REQUIRED.value
    attempt["automatic_assessment"] = Assessment.MANUAL_REQUIRED.value
    _refresh(report)
    path = tmp_path / "review.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(CampaignError, match="confirmed finding"):
        campaign.apply_reviews(path, {attempt["id"]: Assessment.PASS})


def test_pending_review_is_structurally_valid_but_not_verified(tmp_path):
    report = _complete_report(tmp_path)
    attempt = report["repetitions"][0]["attempts"][-1]
    behavior = attempt["fires"][0]["behavior"]
    behavior["judge_label"] = None
    behavior["judge_score"] = None
    behavior["judge_status"] = "failed"
    behavior["judge_error_type"] = "RuntimeError"
    behavior["assessment"] = Assessment.MANUAL_REQUIRED.value
    attempt["fires"][0]["assessment"] = Assessment.MANUAL_REQUIRED.value
    attempt["status"] = AttemptStatus.REVIEW_REQUIRED.value
    attempt["assessment"] = Assessment.MANUAL_REQUIRED.value
    attempt["automatic_assessment"] = Assessment.MANUAL_REQUIRED.value
    _refresh(report)

    validate_campaign_report(report)
    assert "review_pending" in campaign_verification_issues(report)
    assert "campaign_not_complete" in campaign_verification_issues(report)
