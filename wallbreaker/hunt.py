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
    rounds_used: int = 0
    error: str | None = None

    def to_dict(self, include_bodies: bool, bodies: dict | None = None) -> dict:
        payload = {
            "schema": RESULT_SCHEMA,
            "index": self.index,
            "item_id": self.item_id,
            "category": self.category,
            "verdicts": self.verdicts,
            "rounds_used": self.rounds_used,
            "error": self.error,
        }
        if include_bodies and bodies:
            payload["objective"] = bodies.get("objective")
            payload["response"] = bodies.get("response")
        return payload


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _count_labels(verdicts: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for verdict in verdicts:
        label = str(verdict.get("label") or "UNKNOWN")
        counts[label] = counts.get(label, 0) + 1
    return counts


def _summarise(results: list[ItemResult]) -> dict:
    by_category: dict[str, dict] = {}
    for result in results:
        key = result.category or "(none)"
        bucket = by_category.setdefault(key, {"items": 0, "labels": {}})
        bucket["items"] += 1
        for label, count in _count_labels(result.verdicts).items():
            bucket["labels"][label] = bucket["labels"].get(label, 0) + count
    return {"items": len(results), "by_category": by_category}


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
            _captured.append(
                {
                    "label": str(label),
                    "reason": str(reason)[:200],
                    "response_fingerprint": _fingerprint(str(response)),
                }
            )
            _bodies["response"] = str(response)

        registry.ctx.record = record
        registry.ctx.current_objective = objective
        registry.ctx.attacker_model = endpoint.model or ""
        provider = build_provider(endpoint, plan.timeout)
        try:
            await run_autonomous(
                provider,
                registry,
                [user(objective)],
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
        result.rounds_used = len(captured)
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

    print(json.dumps(_summarise(results), indent=2))
    if args.include_bodies:
        print(
            f"Warning: {output} now contains objectives and responses. Treat it as sensitive.",
            file=sys.stderr,
        )
    return 0
