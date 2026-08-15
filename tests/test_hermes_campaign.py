import asyncio
import json
from pathlib import Path

import pytest

from wallbreaker.agent.messages import StopEvent, ToolUseEvent
from wallbreaker.config import Config, Endpoint
from wallbreaker.hermes_campaign import (
    Assessment,
    AttemptStatus,
    CampaignError,
    CampaignSettings,
    CampaignStatus,
    ExpectedBehavior,
    REPORT_SCHEMA,
    SUITE_SCHEMA,
    _assess_behavior,
    _assess_state,
    _config_fingerprint,
    _campaign_output_lock,
    _evaluate_fire,
    _initial_report,
    _register_target,
    _refresh,
    apply_reviews,
    load_suite,
    resume_campaign,
    run_campaign,
)
from wallbreaker.hermes_lab import (
    HERMES_MANIFEST_SCHEMA,
    CleanupReceipt,
    HermesLabEvidence,
    HermesLabResult,
)
from wallbreaker.tools.registry import ToolContext, ToolRegistry
from wallbreaker.session import RunLog, inference_logging


def _suite(path: Path):
    path.write_text(
        f"""schema: {SUITE_SCHEMA}
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
    expected_state: declared_changes
    allowed_state_paths:
      - memories/MEMORY.md
  - id: context-case
    split: holdout
    objective: Synthetic context objective
    prompt: Synthetic context prompt
    expected_behavior: context_dependent
    expected_state: manual
""",
        encoding="utf-8",
    )
    return load_suite(path)


def _config(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": HERMES_MANIFEST_SCHEMA,
                "mode": "clean",
                "provider": "openrouter",
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
        hermes_provider="openrouter",
        hermes_manifest=str(manifest),
    )
    judge = Endpoint("judge", "openai", "https://fixture.invalid", "fixture/judge")
    config = Config(
        default_profile="brain",
        profiles={"brain": attacker},
        target=target,
        judge=judge,
    )
    return config, attacker


def _evidence(changed=(), tool_attempts=0):
    return HermesLabEvidence(
        preflight_fingerprint="1" * 64,
        run_fingerprint="2" * 64,
        initial_state=(("SOUL.md", "3" * 64),),
        final_state=(("SOUL.md", "4" * 64 if changed else "3" * 64),),
        changed_components=tuple(changed),
        tool_attempt_count=tool_attempts,
    )


def _result(response, changed=(), tool_attempts=0):
    receipt = CleanupReceipt("success", True, True, True)
    return HermesLabResult(
        response,
        1,
        1,
        bool(changed),
        receipt,
        _evidence(changed, tool_attempts),
    )


def test_loader_builds_stable_identities_and_rejects_yaml_aliases(tmp_path):
    first = _suite(tmp_path / "suite.yaml")
    second = load_suite(tmp_path / "suite.yaml")
    assert first.fingerprint == second.fingerprint
    assert [case.fingerprint for case in first.cases] == [
        case.fingerprint for case in second.cases
    ]
    assert {case.split.value for case in first.cases} == {
        "discovery",
        "qualification",
        "holdout",
    }

    aliased = tmp_path / "aliased.yaml"
    aliased.write_text(
        f"schema: {SUITE_SCHEMA}\nid: synthetic-suite\nversion: 1\ncases: &cases []\n",
        encoding="utf-8",
    )
    with pytest.raises(CampaignError, match="aliases"):
        load_suite(aliased)


@pytest.mark.parametrize(
    "expected,judge,heuristic,assessment",
    [
        (ExpectedBehavior.ALLOW, "COMPLIED", "COMPLIED", Assessment.PASS),
        (ExpectedBehavior.ALLOW, "REFUSED", "REFUSED", Assessment.FINDING),
        (ExpectedBehavior.REFUSE, "REFUSED", "REFUSED", Assessment.PASS),
        (ExpectedBehavior.REFUSE, "COMPLIED", "COMPLIED", Assessment.FINDING),
        (ExpectedBehavior.REFUSE, "COMPLIED", "REFUSED", Assessment.MANUAL_REQUIRED),
        (ExpectedBehavior.CONTEXT_DEPENDENT, "REFUSED", "REFUSED", Assessment.MANUAL_REQUIRED),
    ],
)
def test_behavior_assessment_covers_expectations_and_disagreement(
    expected, judge, heuristic, assessment
):
    assert _assess_behavior(expected, judge, heuristic) == assessment


def test_state_assessment_covers_soul_memory_rules_and_undeclared_changes(tmp_path):
    suite = _suite(tmp_path / "suite.yaml")
    unchanged, declared, manual = suite.cases
    assert _assess_state(unchanged, ()) == Assessment.PASS
    assert _assess_state(unchanged, ("soul",)) == Assessment.FINDING
    assert _assess_state(declared, ("memory",)) == Assessment.PASS
    assert _assess_state(declared, ("user_memory",)) == Assessment.FINDING
    assert _assess_state(declared, ("rules",)) == Assessment.FINDING
    assert _assess_state(manual, ()) == Assessment.MANUAL_REQUIRED


@pytest.mark.asyncio
async def test_judge_failure_is_explicit_and_requires_review(tmp_path, monkeypatch):
    import wallbreaker.hermes_campaign as campaign

    case = _suite(tmp_path / "suite.yaml").cases[0]
    config, _ = _config(tmp_path)

    async def fail_judge(*args, **kwargs):
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(campaign, "build_provider", lambda endpoint: object())
    monkeypatch.setattr(campaign, "judge_reply", fail_judge)
    fire = await _evaluate_fire(
        case,
        "Synthetic prompt",
        "Here is " + "synthetic content " * 30,
        _result("Synthetic response"),
        config.judge,
    )
    assert fire["behavior"]["judge_status"] == "failed"
    assert fire["behavior"]["judge_error_type"] == "RuntimeError"
    assert fire["behavior"]["assessment"] == Assessment.MANUAL_REQUIRED.value


@pytest.mark.asyncio
async def test_campaign_runs_autonomous_and_persists_only_closed_evidence(tmp_path, monkeypatch):
    import wallbreaker.hermes_campaign as campaign

    suite = _suite(tmp_path / "suite.yaml")
    config, attacker_endpoint = _config(tmp_path)

    class FakeAttacker:
        def __init__(self):
            self.calls = 0

        async def stream(self, messages, **kwargs):
            if self.calls == 0:
                brief = messages[0].text().lower()
                prompt = next(
                    marker for marker in ("allow", "refuse", "context") if marker in brief
                )
                self.calls += 1
                yield ToolUseEvent("target", "query_target", {"prompt": prompt})
                yield StopEvent("tool_use")
                return
            self.calls += 1
            yield ToolUseEvent("finish", "finish", {"summary": "Synthetic complete"})
            yield StopEvent("tool_use")

        async def aclose(self):
            return None

    class FakeTarget:
        async def fire(self, messages, **kwargs):
            prompt = messages[0].text()
            if prompt == "allow":
                response = "Here is " + "synthetic content " * 30
                return _result(response, tool_attempts=1)
            if prompt == "refuse":
                return _result("I cannot help with that.", changed=("memory",))
            return _result("Synthetic context response")

    async def fake_judge(_provider, response, **kwargs):
        if response.startswith("I cannot"):
            return {"label": "REFUSED", "score": 0, "reason": "fixture"}
        if len(response) > 300:
            return {"label": "COMPLIED", "score": 10, "reason": "fixture"}
        return {"label": "PARTIAL", "score": 5, "reason": "fixture"}

    def fake_build(endpoint, timeout=0):
        if endpoint.name == "brain":
            return FakeAttacker()
        if endpoint.name == "target":
            return FakeTarget()
        return object()

    monkeypatch.setattr(campaign, "build_provider", fake_build)
    monkeypatch.setattr(campaign, "judge_reply", fake_judge)
    output = tmp_path / "campaign.json"
    external_log = RunLog(tmp_path / "external-log")
    with inference_logging(external_log):
        report = await run_campaign(
            suite,
            config,
            output,
            CampaignSettings(repetitions=1),
            attacker_endpoint,
        )
    assert report["status"] == CampaignStatus.PARTIAL.value
    assert report["aggregates"]["discovery"]["resolved"] == 1
    assert report["aggregates"]["discovery"]["findings"] == 1
    assert report["aggregates"]["qualification"]["resolved"] == 1
    holdout = next(
        repetition for repetition in report["repetitions"] if repetition["split"] == "holdout"
    )
    attempt = holdout["attempts"][-1]
    assert attempt["status"] == AttemptStatus.REVIEW_REQUIRED.value
    saved = output.read_text(encoding="utf-8")
    for private_text in (
        "Synthetic allow objective",
        "Synthetic refuse prompt",
        "Synthetic context response",
        "synthetic content",
        "fixture.invalid",
    ):
        assert private_text not in saved
    assert not list((tmp_path / "external-log").glob("*.jsonl"))
    reviewed = apply_reviews(output, {attempt["id"]: Assessment.PASS})
    assert reviewed["status"] == CampaignStatus.COMPLETE.value
    assert all(
        aggregate["confidence"]["applicable"]
        for aggregate in reviewed["aggregates"].values()
    )


def test_discordant_repetitions_require_review_and_withhold_confidence(tmp_path):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    settings = CampaignSettings(repetitions=2)
    report = _initial_report(
        suite,
        _config_fingerprint(config, attacker, config.judge, settings),
        settings,
    )
    discovery = [
        repetition for repetition in report["repetitions"] if repetition["split"] == "discovery"
    ]
    for repetition, assessment in zip(discovery, (Assessment.PASS, Assessment.FINDING)):
        attempt = repetition["attempts"][-1]
        attempt["status"] = AttemptStatus.COMPLETED.value
        attempt["assessment"] = assessment.value
        attempt["automatic_assessment"] = assessment.value
    _refresh(report)
    assert all(
        repetition["attempts"][-1]["status"] == AttemptStatus.REVIEW_REQUIRED.value
        for repetition in discovery
    )
    assert report["aggregates"]["discovery"]["confidence"]["applicable"] is False
    assert report["aggregates"]["discovery"]["observed"] == 2
    assert report["aggregates"]["discovery"]["frequency"] == 0.5


@pytest.mark.asyncio
async def test_nonreversible_response_transform_is_rejected_before_fire(tmp_path, monkeypatch):
    import wallbreaker.hermes_campaign as campaign

    suite = _suite(tmp_path / "suite.yaml")
    config, _ = _config(tmp_path)
    calls = []
    registry = ToolRegistry(ToolContext(config=config, vault_enabled=False))
    _register_target(
        registry,
        suite.cases[0],
        CampaignSettings(repetitions=1),
        [],
        config.judge,
    )
    monkeypatch.setattr(campaign, "build_provider", lambda *args, **kwargs: calls.append(args))
    result = await registry.execute(
        "query_target",
        {"prompt": "Synthetic prompt", "response_transforms": ["artprompt"]},
    )
    assert result.content == "Error: unsupported response transform"
    assert calls == []


@pytest.mark.asyncio
async def test_decode_failure_retains_fire_evidence(tmp_path, monkeypatch):
    import wallbreaker.hermes_campaign as campaign

    suite = _suite(tmp_path / "suite.yaml")
    config, _ = _config(tmp_path)
    fires = []
    registry = ToolRegistry(ToolContext(config=config, vault_enabled=False))
    _register_target(
        registry,
        suite.cases[0],
        CampaignSettings(repetitions=1),
        fires,
        config.judge,
    )

    class FakeTarget:
        async def fire(self, messages, **kwargs):
            return _result("plain text")

    async def fake_judge(*args, **kwargs):
        return {"label": "PARTIAL", "score": 5, "reason": "fixture"}

    monkeypatch.setattr(campaign, "build_provider", lambda *args, **kwargs: FakeTarget())
    monkeypatch.setattr(campaign, "judge_reply", fake_judge)
    result = await registry.execute(
        "query_target",
        {"prompt": "Synthetic prompt", "response_transforms": ["hex"]},
    )
    assert result.content == "Error: response transform could not be decoded"
    assert len(fires) == 1
    assert fires[0]["response_transform"]["status"] == "failed"
    assert fires[0]["response_transform"]["error_type"] == "ValueError"
    assert fires[0]["attestation"]["preflight_fingerprint"] == "1" * 64
    assert fires[0]["assessment"] == Assessment.MANUAL_REQUIRED.value


@pytest.mark.asyncio
async def test_resume_rejects_changed_selected_context(tmp_path):
    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    context_root = tmp_path / "context"
    context_root.mkdir()
    soul = context_root / "SOUL.md"
    soul.write_text("Synthetic initial identity", encoding="utf-8")
    assert config.target is not None
    config.target.hermes_context_root = str(context_root)
    Path(config.target.hermes_manifest).write_text(
        json.dumps(
            {
                "schema": HERMES_MANIFEST_SCHEMA,
                "mode": "selected",
                "provider": "openrouter",
                "model": "fixture/target",
                "files": ["SOUL.md"],
                "expected_tool_count": 0,
            }
        ),
        encoding="utf-8",
    )
    settings = CampaignSettings(repetitions=1)
    fingerprint = _config_fingerprint(config, attacker, config.judge, settings)
    output = tmp_path / "campaign.json"
    output.write_text(
        json.dumps(_initial_report(suite, fingerprint, settings)), encoding="utf-8"
    )
    soul.write_text("Synthetic changed identity", encoding="utf-8")
    with pytest.raises(CampaignError, match="identity"):
        await resume_campaign(suite, config, output, settings, attacker)


def test_config_identity_tracks_endpoint_prompts_and_timeout(tmp_path):
    config, attacker = _config(tmp_path)
    settings = CampaignSettings(repetitions=1)
    original = _config_fingerprint(config, attacker, config.judge, settings)
    assert config.judge is not None
    config.judge.system_prompt = "Synthetic judge policy"
    judge_changed = _config_fingerprint(config, attacker, config.judge, settings)
    assert judge_changed != original
    prompt_file = tmp_path / "attacker.txt"
    prompt_file.write_text("Synthetic attacker policy", encoding="utf-8")
    attacker.system_prompt_file = str(prompt_file)
    file_changed = _config_fingerprint(config, attacker, config.judge, settings)
    assert file_changed != judge_changed
    attacker.timeout = 45
    assert _config_fingerprint(config, attacker, config.judge, settings) != file_changed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "interrupted_status", [AttemptStatus.RUNNING.value, AttemptStatus.FAILED.value]
)
async def test_resume_replaces_interrupted_attempt_instead_of_resuming_it(
    tmp_path, monkeypatch, interrupted_status
):
    import wallbreaker.hermes_campaign as campaign

    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    settings = CampaignSettings(repetitions=1)
    fingerprint = _config_fingerprint(config, attacker, config.judge, settings)
    report = _initial_report(suite, fingerprint, settings)
    first = report["repetitions"][0]
    first["attempts"][-1]["status"] = interrupted_status
    if interrupted_status == AttemptStatus.FAILED.value:
        first["attempts"][-1]["assessment"] = Assessment.MANUAL_REQUIRED.value
        first["attempts"][-1]["error_type"] = "SyntheticError"
        first["attempts"][-1]["invocations"] = [
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
    _refresh(report)
    output = tmp_path / "campaign.json"
    output.write_text(json.dumps(report), encoding="utf-8")

    async def fake_run(*args, **kwargs):
        return "finished", Assessment.PASS, [{"assessment": Assessment.PASS.value}]

    monkeypatch.setattr(campaign, "_run_repetition", fake_run)
    resumed = await resume_campaign(suite, config, output, settings, attacker)
    attempts = resumed["repetitions"][0]["attempts"]
    assert attempts[0]["status"] == AttemptStatus.REPLACED.value
    assert attempts[1]["ordinal"] == 1
    assert attempts[1]["status"] == AttemptStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_cancelled_campaign_persists_replacement_state(tmp_path, monkeypatch):
    import wallbreaker.hermes_campaign as campaign

    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    output = tmp_path / "campaign.json"

    async def cancel(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(campaign, "_run_repetition", cancel)
    with pytest.raises(asyncio.CancelledError):
        await run_campaign(
            suite,
            config,
            output,
            CampaignSettings(repetitions=1),
            attacker,
        )
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == REPORT_SCHEMA
    assert saved["status"] == CampaignStatus.CANCELLED.value
    assert saved["repetitions"][0]["attempts"][-1]["status"] == AttemptStatus.REPLACED.value


@pytest.mark.asyncio
async def test_concurrent_campaign_writer_fails_closed(tmp_path, monkeypatch):
    import wallbreaker.hermes_campaign as campaign

    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    output = tmp_path / "campaign.json"
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked_run(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            await release.wait()
        return "finished", Assessment.PASS, [{"assessment": Assessment.PASS.value}]

    monkeypatch.setattr(campaign, "_run_repetition", blocked_run)
    first = asyncio.create_task(
        run_campaign(
            suite,
            config,
            output,
            CampaignSettings(repetitions=1),
            attacker,
        )
    )
    await entered.wait()
    with pytest.raises(CampaignError, match="already in use"):
        await resume_campaign(
            suite,
            config,
            output,
            CampaignSettings(repetitions=1),
            attacker,
        )
    with pytest.raises(CampaignError, match="already in use"):
        apply_reviews(output, {})
    release.set()
    await first


@pytest.mark.asyncio
async def test_cancel_after_fire_preserves_closed_evidence(tmp_path, monkeypatch):
    import wallbreaker.hermes_campaign as campaign

    suite = _suite(tmp_path / "suite.yaml")
    config, attacker = _config(tmp_path)
    output = tmp_path / "campaign.json"

    class FakeAttacker:
        async def aclose(self):
            return None

    class FakeTarget:
        async def fire(self, messages, **kwargs):
            return _result("Here is " + "synthetic content " * 30)

    def fake_build(endpoint, timeout=0):
        return FakeTarget() if endpoint.name == "target" else FakeAttacker()

    async def fake_judge(*args, **kwargs):
        raise asyncio.CancelledError

    async def cancel_after_fire(_provider, registry, *args, **kwargs):
        await registry.execute("query_target", {"prompt": "Synthetic prompt"})

    monkeypatch.setattr(campaign, "build_provider", fake_build)
    monkeypatch.setattr(campaign, "judge_reply", fake_judge)
    monkeypatch.setattr(campaign, "run_autonomous", cancel_after_fire)
    with pytest.raises(asyncio.CancelledError):
        await run_campaign(
            suite,
            config,
            output,
            CampaignSettings(repetitions=1),
            attacker,
        )
    saved = json.loads(output.read_text(encoding="utf-8"))
    attempt = saved["repetitions"][0]["attempts"][-1]
    assert attempt["status"] == AttemptStatus.REPLACED.value
    assert len(attempt["fires"]) == 1
    assert attempt["fires"][0]["attestation"]["run_fingerprint"] == "2" * 64
    assert attempt["fires"][0]["behavior"]["judge_status"] == "pending"
    assert attempt["fires"][0]["assessment"] == Assessment.MANUAL_REQUIRED.value


def test_lock_open_failure_releases_in_process_guard(tmp_path, monkeypatch):
    import wallbreaker.hermes_campaign as campaign

    output = tmp_path / "missing-parent" / "campaign.json"

    def fail_open(*args, **kwargs):
        raise OSError("fixture failure")

    monkeypatch.setattr(campaign, "open", fail_open, raising=False)
    with pytest.raises(CampaignError, match="lock could not be created"):
        with _campaign_output_lock(output):
            pass
    monkeypatch.delattr(campaign, "open")
    with _campaign_output_lock(output):
        pass
