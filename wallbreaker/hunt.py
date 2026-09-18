"""Sweep a behavior battery from a plain command line, for an agent to drive.

The interactive terminal can sample a battery, but an agent cannot drive a TUI. ``hunt`` walks one
battery against the configured target, one behavior per item, and grades each reply with the same
judge as the rest of the harness.

It fires the behavior itself instead of asking an agent to do it. That is deliberate: when the fire
was left to an agent, the agent chose a tool without chain-of-thought recovery or stop-reason
reporting, four items produced no verdict at all, and six empty replies were graded as refusals. A
sweep has to measure what it claims to measure, so the shot, the ceiling and the recording are fixed
here.

The result file holds verdicts, counts and fingerprints. The prompt and the response are written
only with ``--include-bodies``, and then the file is sensitive engagement material.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import datasets

SCHEMA = "wallbreaker.hunt-plan/v1"
RESULT_SCHEMA = "wallbreaker.hunt-result/v1"

# Output ceiling for every fire. The target tool defaults to 1024, which a reasoning model can
# spend on its own thinking and leave the reply empty.
TARGET_MAX_TOKENS = 4096


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from None
    if number < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def add_hunt_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "hunt", help="Sweep a behavior battery against the configured target"
    )
    parser.add_argument("--battery", required=True, help="Battery name or file:PATH")
    parser.add_argument("--category", help="Semantic category filter")
    parser.add_argument("--items", dest="items", type=_positive_int, required=True,
                        help="How many behaviors to run (required: no silent default)")
    parser.add_argument("--rounds", type=_positive_int, required=True,
                        help="Accepted for compatibility; the sweep fires once per behavior")
    parser.add_argument("--seed", type=int, default=0, help="Sampling seed (default 0)")
    parser.add_argument("--timeout", type=float, default=60.0, help="Per-request timeout in seconds")
    parser.add_argument("--max-tokens", type=_positive_int, default=TARGET_MAX_TOKENS,
                        help=f"Output ceiling per fire (default {TARGET_MAX_TOKENS})")
    parser.add_argument("--config", help="Path to config.toml")
    parser.add_argument("--target", help="Target profile name to attack")
    parser.add_argument("--output", required=True, help="JSONL result path")
    parser.add_argument("--include-bodies", action="store_true",
                        help="Also write the behavior and the reply. The output becomes sensitive.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and stop")
    parser.add_argument("--authorized", action="store_true", help="Confirm a previously shown plan")
    parser.add_argument("--confirm", help="Token printed by an identical --dry-run")


@dataclass(frozen=True)
class HuntPlan:
    """Everything that decides cost, frozen so a token cannot be reused for a different sweep."""

    battery: str
    category: str | None
    items: int
    seed: int
    timeout: float
    max_tokens: int
    target: str
    judge: str

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "battery": self.battery,
            "category": self.category,
            "items": self.items,
            "seed": self.seed,
            "timeout": self.timeout,
            "max_tokens": self.max_tokens,
            "target": self.target,
            "judge": self.judge,
        }

    def token(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


@dataclass
class ItemResult:
    index: int
    item_id: str | None
    category: str | None
    label: str | None = None
    reason: str = ""
    graded_by: str | None = None
    stop_reason: str | None = None
    response_empty: bool = False
    truncated: bool = False
    response_chars: int = 0
    response_fingerprint: str | None = None
    error: str | None = None
    bodies: dict = field(default_factory=dict)

    @property
    def measured(self) -> bool:
        """An item counts only when its reply carried content.

        A reply that came back empty says nothing about the target's willingness; grading it as a
        refusal reports a wall that was never there.
        """
        return bool(self.label) and not self.response_empty

    def to_dict(self, include_bodies: bool) -> dict:
        payload = {
            "schema": RESULT_SCHEMA,
            "index": self.index,
            "item_id": self.item_id,
            "category": self.category,
            "label": self.label,
            "graded_by": self.graded_by,
            "reason": self.reason[:200],
            "stop_reason": self.stop_reason,
            "response_empty": self.response_empty,
            "truncated": self.truncated,
            "response_chars": self.response_chars,
            "response_fingerprint": self.response_fingerprint,
            "measured": self.measured,
            "error": self.error,
        }
        if include_bodies:
            payload["behavior"] = self.bodies.get("behavior")
            payload["response"] = self.bodies.get("response")
        return payload


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _summarise(results: list[ItemResult]) -> dict:
    by_category: dict[str, dict] = {}
    measured = 0
    empty = 0
    for result in results:
        key = result.category or "(none)"
        bucket = by_category.setdefault(
            key, {"items": 0, "measured_items": 0, "empty_replies": 0, "labels": {}, "errors": 0}
        )
        bucket["items"] += 1
        if result.error:
            bucket["errors"] += 1
        if result.response_empty:
            empty += 1
            bucket["empty_replies"] += 1
        if result.measured:
            measured += 1
            bucket["measured_items"] += 1
            label = str(result.label)
            bucket["labels"][label] = bucket["labels"].get(label, 0) + 1
    return {
        "items": len(results),
        "measured_items": measured,
        "unmeasured_items": len(results) - measured,
        "empty_replies": empty,
        "by_category": by_category,
    }


def plan_hunt(args, config) -> HuntPlan:
    target_endpoint = getattr(config, "target", None)
    judge_endpoint = getattr(config, "judge", None) or target_endpoint
    return HuntPlan(
        battery=args.battery,
        category=args.category,
        items=args.items,
        seed=args.seed,
        timeout=args.timeout,
        max_tokens=args.max_tokens,
        target=getattr(target_endpoint, "model", "") or "(no target)",
        judge=getattr(judge_endpoint, "model", "") or "(no judge)",
    )


def _load_behaviors(plan: HuntPlan) -> list[dict]:
    from .battery_cli import ensure_battery

    loader = datasets.get(plan.battery)
    error = ensure_battery(loader)
    if error:
        raise RuntimeError(error)
    rows = loader.sample(plan.category, plan.items, plan.seed)
    if not rows:
        raise RuntimeError(
            f"no behaviors for category {plan.category!r}; "
            f"categories: {', '.join(loader.categories())}"
        )
    return rows


async def _sweep(plan: HuntPlan, config, behaviors: list[dict]) -> list[ItemResult]:
    from .agent.messages import user
    from .judging import grade
    from .providers.factory import build_provider
    from .tools._util import complete_untruncated

    target_endpoint = getattr(config, "target", None)
    if target_endpoint is None:
        raise RuntimeError("the configuration has no target to attack")
    judge_endpoint = getattr(config, "judge", None) or target_endpoint
    provider = build_provider(target_endpoint, plan.timeout)
    results: list[ItemResult] = []

    try:
        for index, row in enumerate(behaviors, 1):
            behavior = str(row.get("behavior") or "")
            result = ItemResult(index=index, item_id=row.get("id"), category=row.get("category"))
            result.bodies = {"behavior": behavior, "response": None}
            try:
                reply, reasoning, stop, truncated = await complete_untruncated(
                    provider, [user(behavior)], None, plan.max_tokens
                )
                empty = not (reply or "").strip()
                result.truncated = truncated
                result.stop_reason = stop
                result.response_empty = empty
                result.response_chars = len(reply or "")
                result.response_fingerprint = _fingerprint(reply or "")
                result.bodies["response"] = reply
                if empty:
                    # Still graded, so the label is recorded, but `measured` stays False and the
                    # summary reports the emptiness instead of counting it as a verdict.
                    result.reason = "the target returned no content"
                    result.graded_by = "empty"
                    result.label = None
                else:
                    label, _score, reason, source = await grade(
                        judge_endpoint, reply, payload=behavior, objective=behavior,
                        reasoning=reasoning or "",
                    )
                    result.label = label
                    result.reason = reason
                    result.graded_by = source
            except Exception as exc:  # noqa: BLE001 - one bad item must not abort the sweep
                result.error = f"{type(exc).__name__}: {exc}"[:200]
            results.append(result)
            shown = "empty" if result.response_empty else (result.label or result.error or "?")
            print(f"[{index}/{len(behaviors)}] {result.item_id or ''} -> {shown}", file=sys.stderr)
    finally:
        close = getattr(provider, "aclose", None)
        if close is not None:
            await close()
    return results


def run_hunt_cli(args) -> int:
    from .config import ConfigError, load_config

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"[config error] {exc}", file=sys.stderr)
        return 1

    if getattr(args, "target", None):
        from .cli import apply_target_overrides

        apply_target_overrides(config, args)

    plan = plan_hunt(args, config)
    token = plan.token()

    if args.dry_run:
        print(json.dumps({**plan.to_dict(), "token": token}, indent=2))
        print(
            "Dry run only: no provider was built and nothing was spent. "
            "Approve this exact plan and rerun with --authorized --confirm TOKEN.",
            file=sys.stderr,
        )
        return 0

    if not args.authorized or not args.confirm or args.confirm != token:
        print(
            "Refusing to run without an approved plan. Run the same command with --dry-run, "
            "review it, and add --authorized --confirm TOKEN.",
            file=sys.stderr,
        )
        return 2

    try:
        behaviors = _load_behaviors(plan)
    except (KeyError, RuntimeError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    results = asyncio.run(_sweep(plan, config, behaviors))

    output = Path(args.output)
    try:
        with output.open("w", encoding="utf-8") as handle:
            for result in results:
                handle.write(json.dumps(result.to_dict(args.include_bodies), ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"Error: could not write {output}: {exc}", file=sys.stderr)
        return 1

    summary = _summarise(results)
    print(json.dumps(summary, indent=2))
    if summary["empty_replies"]:
        print(
            f"Warning: {summary['empty_replies']} repl(ies) came back empty and are not counted as "
            "verdicts. Check the stop_reason in the file: an empty reply is not a refusal.",
            file=sys.stderr,
        )
    if args.include_bodies:
        print(
            f"Warning: {output} now contains behaviors and replies. Treat it as sensitive.",
            file=sys.stderr,
        )
    return 0
