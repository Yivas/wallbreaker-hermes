"""Sweep a behavior battery from a plain command line, for an agent to drive.

The interactive terminal can sample a battery, but an agent cannot drive a TUI. ``hunt`` walks one
battery against the configured target, one behavior per item, reusing the same autonomous loop and
judge as the rest of the harness. It writes one JSON line per item with verdicts, counts and
fingerprints — never the prompt or the response unless the operator asks for them explicitly, in
which case the file becomes sensitive engagement material.
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

# Output ceiling asked of every fire. The target tool's own default is 1024, which is not enough
# for a model that reasons first: the reply comes back empty and the judge then sees nothing.
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
                        help="Autonomous round cap per behavior (required: no silent default)")
    parser.add_argument("--seed", type=int, default=0, help="Sampling seed (default 0)")
    parser.add_argument("--timeout", type=float, default=60.0, help="Per-request timeout in seconds")
    parser.add_argument("--config", help="Path to config.toml")
    parser.add_argument("--profile", help="Attacker profile name")
    parser.add_argument("--target", help="Target profile name to attack")
    parser.add_argument("--output", required=True, help="JSONL result path")
    parser.add_argument("--include-bodies", action="store_true",
                        help="Also write the objective and the response. The output becomes sensitive.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and stop")
    parser.add_argument("--authorized", action="store_true", help="Confirm a previously shown plan")
    parser.add_argument("--confirm", help="Token printed by an identical --dry-run")


@dataclass(frozen=True)
class HuntPlan:
    """Everything that decides cost, frozen so a token cannot be reused for a different sweep."""

    battery: str
    category: str | None
    items: int
    rounds: int
    seed: int
    timeout: float
    profile: str | None
    target: str
    attacker: str

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "battery": self.battery,
            "category": self.category,
            "items": self.items,
            "rounds": self.rounds,
            "seed": self.seed,
            "timeout": self.timeout,
            "profile": self.profile,
            "target": self.target,
            "attacker": self.attacker,
        }

    def token(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


@dataclass
class ItemResult:
    index: int
    item_id: str | None
    category: str | None
    verdicts: list[dict] = field(default_factory=list)
    graded_fires: int = 0
    error: str | None = None

    @property
    def measured(self) -> bool:
        """An item counts only when at least one graded reply carried content.

        A reply that came back empty is not a refusal: the target said nothing, and a judge reading
        that emptiness as REFUSED would report a wall that was never there.
        """
        return any(not verdict.get("response_empty") for verdict in self.verdicts)

    def to_dict(self, include_bodies: bool, bodies: dict | None = None) -> dict:
        payload = {
            "schema": RESULT_SCHEMA,
            "index": self.index,
            "item_id": self.item_id,
            "category": self.category,
            "verdicts": self.verdicts,
            "graded_fires": self.graded_fires,
            "measured": self.measured,
            "error": self.error,
        }
        if include_bodies and bodies:
            payload["objective"] = bodies.get("objective")
            payload["response"] = bodies.get("response")
        return payload


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _empty_fingerprint() -> str:
    return _fingerprint("")


def _count_labels(verdicts: list[dict]) -> dict[str, int]:
    """Labels of graded replies that actually carried content.

    Replies with no content are excluded: an empty answer cannot say anything about the target's
    willingness, and counting it as REFUSED would invent a result.
    """
    counts: dict[str, int] = {}
    for verdict in verdicts:
        if verdict.get("response_empty"):
            continue
        label = str(verdict.get("label") or "UNKNOWN")
        counts[label] = counts.get(label, 0) + 1
    return counts


def _summarise(results: list[ItemResult]) -> dict:
    by_category: dict[str, dict] = {}
    measured = 0
    empty_replies = 0
    for result in results:
        key = result.category or "(none)"
        bucket = by_category.setdefault(
            key, {"items": 0, "measured_items": 0, "graded_fires": 0, "empty_replies": 0, "labels": {}}
        )
        bucket["items"] += 1
        bucket["graded_fires"] += result.graded_fires
        bucket["empty_replies"] += sum(1 for v in result.verdicts if v.get("response_empty"))
        if result.measured:
            measured += 1
            bucket["measured_items"] += 1
        for label, count in _count_labels(result.verdicts).items():
            bucket["labels"][label] = bucket["labels"].get(label, 0) + count
    empty_replies = sum(1 for r in results for v in r.verdicts if v.get("response_empty"))
    return {
        "items": len(results),
        "measured_items": measured,
        "unmeasured_items": len(results) - measured,
        "empty_replies": empty_replies,
        "by_category": by_category,
    }


def plan_hunt(args, config) -> HuntPlan:
    target_endpoint = getattr(config, "target", None)
    target_name = getattr(target_endpoint, "model", "") or "(no target)"
    attacker_name = ""
    try:
        attacker_name = config.profile(getattr(args, "profile", None)).model or ""
    except Exception:  # noqa: BLE001 - the plan still prints without a resolved attacker
        attacker_name = ""
    return HuntPlan(
        battery=args.battery,
        category=args.category,
        items=args.items,
        rounds=args.rounds,
        seed=args.seed,
        timeout=args.timeout,
        profile=getattr(args, "profile", None),
        target=target_name,
        attacker=attacker_name,
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
            f"no behaviors for category {plan.category!r}; categories: {', '.join(loader.categories())}"
        )
    return rows


async def _run_items(plan: HuntPlan, config, behaviors: list[dict]) -> list[ItemResult]:
    from .agent.loop import run_autonomous
    from .agent.messages import user
    from .prompts import compose_system
    from .providers.factory import build_provider
    from .tools import build_registry

    endpoint = config.profile(plan.profile)
    system = compose_system(endpoint, None)
    results: list[ItemResult] = []
    bodies_by_index: dict[int, dict] = {}

    for index, row in enumerate(behaviors, 1):
        objective = str(row.get("behavior") or "")
        result = ItemResult(index=index, item_id=row.get("id"), category=row.get("category"))
        registry = build_registry(config)
        captured: list[dict] = []
        bodies: dict = {"objective": objective, "response": None}

        def record(payload, response, label, reason, *_rest, _captured=captured, _bodies=bodies):
            text = "" if response is None else str(response)
            _captured.append(
                {
                    "label": str(label),
                    "reason": str(reason)[:200],
                    "response_fingerprint": _fingerprint(text),
                    # An empty reply is reported as such instead of being counted as a refusal.
                    "response_empty": not text.strip(),
                }
            )
            _bodies["response"] = text

        registry.ctx.record = record
        registry.ctx.current_objective = objective
        registry.ctx.attacker_model = endpoint.model or ""
        provider = build_provider(endpoint, plan.timeout)
        # The target tool defaults to 1024 output tokens, which a reasoning model can spend on its
        # own thinking and leave the reply empty. Telling the attacker the ceiling avoids the
        # dominant "it came back empty" failure in this sweep.
        brief = "\n\n".join(
            (
                objective,
                f"Fire at the target with max_tokens={TARGET_MAX_TOKENS} so a reasoning model still "
                "has room to answer after thinking.",
            )
        )
        try:
            await run_autonomous(
                provider,
                registry,
                [user(brief)],
                system=system,
                max_rounds=plan.rounds,
                max_tokens=getattr(config, "attacker_max_tokens", 4096) or 4096,
                max_iters=1,
            )
        except Exception as exc:  # noqa: BLE001 - one bad item must not abort the sweep
            result.error = f"{type(exc).__name__}: {exc}"[:200]
        finally:
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()
        result.verdicts = captured
        result.graded_fires = len(captured)
        if not captured:
            result.error = "no graded fire: the attacker never fired at the target"
        results.append(result)
        bodies_by_index[index] = bodies
        print(
            f"[{index}/{len(behaviors)}] {result.item_id or ''} "
            f"{_count_labels(captured) or '(no verdict)'}",
            file=sys.stderr,
        )
    return results, bodies_by_index


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
    payload = plan.to_dict()
    token = plan.token()

    if args.dry_run:
        print(json.dumps({**payload, "token": token}, indent=2))
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

    results, bodies_by_index = asyncio.run(_run_items(plan, config, behaviors))

    output = Path(args.output)
    try:
        with output.open("w", encoding="utf-8") as handle:
            for result in results:
                handle.write(
                    json.dumps(
                        result.to_dict(
                            args.include_bodies, bodies_by_index.get(result.index)
                        ),
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    except OSError as exc:
        print(f"Error: could not write {output}: {exc}", file=sys.stderr)
        return 1

    summary = _summarise(results)
    print(json.dumps(summary, indent=2))
    if summary["empty_replies"]:
        print(
            f"Warning: {summary['empty_replies']} graded repl(ies) came back empty and are excluded "
            "from the label counts. An empty reply is not a refusal: raise the target's max_tokens "
            "or inspect why the provider returned no content.",
            file=sys.stderr,
        )
    if args.include_bodies:
        print(
            f"Warning: {output} now contains objectives and responses. Treat it as sensitive.",
            file=sys.stderr,
        )
    return 0
