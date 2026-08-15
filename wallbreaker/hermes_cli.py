from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import sys

from dotenv import load_dotenv

from . import __version__
from .config import ConfigError, load_config
from .hermes_campaign import (
    Assessment,
    AttemptStatus,
    CampaignError,
    CampaignSettings,
    build_campaign_plan,
    campaign_verification_issues,
    load_campaign_report,
    load_suite,
    resume_campaign,
    run_campaign,
    apply_reviews,
    validate_campaign_report,
)
from .hermes_lab import (
    HERMES_BASELINE_RELEASE,
    HERMES_BASELINE_SHA,
    HERMES_BASELINE_VERSION,
)
from .providers.base import ProviderError


EVENT_SCHEMA = "wallbreaker.hermes-cli-event/v1"


class EventWriter:
    def __init__(self, command: str, artifact: str) -> None:
        self.command = command
        self.artifact = artifact
        self.sequence = 0

    def emit(self, event: str, data: dict | None = None) -> None:
        self.sequence += 1
        payload = {
            "schema": EVENT_SCHEMA,
            "seq": self.sequence,
            "command": self.command,
            "event": event,
            "artifact": self.artifact,
            "data": data or {},
        }
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def _bounded_int(minimum: int, maximum: int):
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("expected an integer") from exc
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(f"expected {minimum}..{maximum}")
        return parsed

    return parse


def _bounded_float(minimum: float, maximum: float):
    def parse(value: str) -> float:
        try:
            parsed = float(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("expected a number") from exc
        if not minimum < parsed <= maximum:
            raise argparse.ArgumentTypeError(f"expected >{minimum:g}..{maximum:g}")
        return parsed

    return parse


def add_hermes_parser(subparsers) -> None:
    hermes = subparsers.add_parser(
        "hermes", help="Run, review, and verify Hermes laboratory campaigns"
    )
    actions = hermes.add_subparsers(dest="hermes_action", required=True)

    run = actions.add_parser("run", help="Plan or run an authorized campaign")
    run.add_argument("suite", help="Campaign suite YAML")
    run.add_argument("--output", required=True, help="Campaign report JSON")
    run.add_argument("--config", help="Path to config.toml")
    run.add_argument("--profile", help="Attacker profile name")
    run.add_argument("--repetitions", type=_bounded_int(1, 10), default=3)
    run.add_argument("--max-rounds", type=_bounded_int(1, 50), default=12)
    run.add_argument("--max-fires", type=_bounded_int(1, 20), default=12)
    run.add_argument("--attacker-max-tokens", type=_bounded_int(1, 131072), default=8192)
    run.add_argument("--target-max-tokens", type=_bounded_int(1, 8192), default=1024)
    run.add_argument("--timeout", type=_bounded_float(0, 600), default=90.0)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--authorized", action="store_true")
    run.add_argument("--confirm", help="Confirmation token from an identical dry run")

    review = actions.add_parser("review", help="List or resolve pending reviews")
    review.add_argument("run", help="Campaign report JSON")
    review.add_argument(
        "--set",
        dest="decisions",
        action="append",
        default=[],
        metavar="ATTEMPT=pass|finding",
    )

    verify = actions.add_parser("verify", help="Verify report structure and closed evidence")
    verify.add_argument("run", help="Campaign report JSON")


def _settings(args: argparse.Namespace) -> CampaignSettings:
    return CampaignSettings(
        repetitions=args.repetitions,
        max_rounds=args.max_rounds,
        max_fires=args.max_fires,
        attacker_max_tokens=args.attacker_max_tokens,
        target_max_tokens=args.target_max_tokens,
        timeout=args.timeout,
    )


def _summary(report: dict) -> dict:
    report = validate_campaign_report(report)
    pending = [
        attempt["id"]
        for repetition in report["repetitions"]
        if (attempt := repetition["attempts"][-1])["status"]
        == AttemptStatus.REVIEW_REQUIRED.value
    ]
    return {
        "status": report["status"],
        "versions": {
            "wallbreaker": __version__,
            "hermes_release": HERMES_BASELINE_RELEASE,
            "hermes_agent": HERMES_BASELINE_VERSION,
            "hermes_commit": HERMES_BASELINE_SHA,
            "suite": report["versions"]["suite"],
        },
        "suite_fingerprint": report["suite_fingerprint"],
        "config_fingerprint": report["config_fingerprint"],
        "aggregates": report["aggregates"],
        "pending_review_ids": pending,
    }


def _result_code(report: dict) -> int:
    latest = [repetition["attempts"][-1] for repetition in report["repetitions"]]
    if report["status"] == "failed" or any(
        attempt["status"] == AttemptStatus.FAILED.value for attempt in latest
    ):
        return 1
    return 0 if not campaign_verification_issues(report) else 2


def _parse_decisions(values: list[str]) -> dict[str, Assessment]:
    decisions = {}
    for value in values:
        attempt_id, separator, raw_decision = value.partition("=")
        if not separator or not attempt_id or attempt_id in decisions:
            raise CampaignError("Review decisions must use unique ATTEMPT=pass|finding values.")
        try:
            decision = Assessment(raw_decision)
        except ValueError as exc:
            raise CampaignError("Manual review must be pass or finding.") from exc
        if decision == Assessment.MANUAL_REQUIRED:
            raise CampaignError("Manual review must be pass or finding.")
        decisions[attempt_id] = decision
    return decisions


def _run_command(args: argparse.Namespace, writer: EventWriter) -> int:
    if not args.dry_run and (not args.authorized or not args.confirm):
        writer.emit(
            "result",
            {"status": "authorization_required", "exit_code": 3},
        )
        return 3
    load_dotenv()
    config = load_config(args.config)
    attacker = config.profile(args.profile)
    settings = _settings(args)
    suite = load_suite(args.suite)
    plan = build_campaign_plan(
        suite,
        config,
        args.output,
        settings,
        attacker,
        resume=args.resume,
    )
    writer.emit("plan.validated", plan)
    if args.dry_run:
        writer.emit("result", {"status": "dry_run", "exit_code": 0})
        return 0
    if not hmac.compare_digest(args.confirm, plan["confirmation"]):
        writer.emit(
            "result",
            {"status": "confirmation_mismatch", "exit_code": 3},
        )
        return 3

    async def execute():
        def callback(event, data):
            writer.emit(event, dict(data))

        if args.resume:
            return await resume_campaign(
                suite,
                config,
                args.output,
                settings,
                attacker,
                event_sink=callback,
                expected_plan=plan,
            )
        return await run_campaign(
            suite,
            config,
            args.output,
            settings,
            attacker,
            event_sink=callback,
            expected_plan=plan,
        )

    try:
        report = asyncio.run(execute())
    except (KeyboardInterrupt, asyncio.CancelledError):
        writer.emit("result", {"status": "cancelled", "exit_code": 130})
        return 130
    code = _result_code(report)
    writer.emit("result", {**_summary(report), "exit_code": code})
    return code


def _review_command(args: argparse.Namespace, writer: EventWriter) -> int:
    report = load_campaign_report(args.run)
    if not args.decisions:
        summary = _summary(report)
        code = 2 if summary["pending_review_ids"] else _result_code(report)
        writer.emit("review.pending", summary)
        writer.emit("result", {**summary, "exit_code": code})
        return code
    decisions = _parse_decisions(args.decisions)
    writer.emit("review.started", {"decision_count": len(decisions)})
    report = apply_reviews(args.run, decisions)
    code = _result_code(report)
    writer.emit("review.applied", {"decision_count": len(decisions)})
    writer.emit("result", {**_summary(report), "exit_code": code})
    return code


def _verify_command(args: argparse.Namespace, writer: EventWriter) -> int:
    report = load_campaign_report(args.run)
    issues = campaign_verification_issues(report)
    code = 0 if not issues else 2
    writer.emit("verify.finished", {"issues": list(issues), **_summary(report)})
    writer.emit("result", {"status": "verified" if not issues else "incomplete", "exit_code": code})
    return code


def run_hermes_cli(args: argparse.Namespace) -> int:
    artifact = getattr(args, "output", None) or getattr(args, "run", "")
    writer = EventWriter(args.hermes_action, artifact)
    try:
        if args.hermes_action == "run":
            return _run_command(args, writer)
        if args.hermes_action == "review":
            return _review_command(args, writer)
        return _verify_command(args, writer)
    except (KeyboardInterrupt, asyncio.CancelledError):
        writer.emit("result", {"status": "cancelled", "exit_code": 130})
        return 130
    except (CampaignError, ConfigError, ProviderError, OSError, TimeoutError) as exc:
        print(f"[hermes error] {exc}", file=sys.stderr)
        writer.emit("result", {"status": "error", "exit_code": 1})
        return 1
