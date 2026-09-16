"""Read the bundled behavior batteries without the interactive terminal.

The terminal can sample a battery, but an agent cannot drive a TUI. This subcommand exposes the
same loaders on a plain command line so a coordinator can list and sample behaviors, print JSON for
a machine, or point at an operator battery with ``file:PATH``.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys

from . import datasets


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from None
    if number < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def add_battery_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "battery", help="List or sample a bundled behavior battery without the terminal"
    )
    parser.add_argument(
        "source",
        help="Battery name or file:PATH. Known: " + ", ".join(datasets.sources()),
    )
    parser.add_argument("--category", help="Semantic category filter")
    parser.add_argument("--n", type=_positive_int, default=10, help="How many behaviors (default 10)")
    parser.add_argument("--seed", type=int, default=0, help="Sampling seed (default 0)")
    parser.add_argument("--json", action="store_true", help="Print a JSON object instead of a list")


def ensure_battery(loader) -> str | None:
    """Fetch a battery if its loader needs it.

    Bundled loaders expose an awaitable ``ensure``; the local loader has none. Getting this wrong
    silently returns a coroutine and the sample comes back empty, so both cases are handled here for
    every command that reads a battery.
    """
    ensure = getattr(loader, "ensure", None)
    if ensure is None:
        return None
    outcome = ensure()
    if inspect.isawaitable(outcome):
        outcome = asyncio.run(outcome)
    return outcome


def _payload(source: str, category: str | None, rows: list[dict]) -> dict:
    return {
        "schema": "wallbreaker.battery-sample/v1",
        "source": source,
        "category": category,
        "count": len(rows),
        "behaviors": [
            {
                "id": row.get("id"),
                "behavior": row.get("behavior"),
                "category": row.get("category"),
                "benign": row.get("benign"),
            }
            for row in rows
        ],
    }


def run_battery_cli(args) -> int:
    try:
        loader = datasets.get(args.source)
    except KeyError as exc:
        # The loader is the single source of truth for valid names and for the local-battery
        # spelling, so its message is passed through instead of duplicated here.
        print(str(exc).strip("'"), file=sys.stderr)
        return 2

    error = ensure_battery(loader)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    try:
        rows = loader.sample(args.category, args.n, args.seed)
    except (KeyError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    categories = loader.categories()
    if not rows:
        print(
            f"No behaviors for category {args.category!r}. "
            f"Categories: {', '.join(categories)}",
            file=sys.stderr,
        )
        return 2

    if args.json:
        print(json.dumps(_payload(args.source, args.category, rows), ensure_ascii=False, indent=2))
        return 0

    header = f"{len(rows)} behaviors from {args.source}"
    if args.category:
        header += f" ({args.category})"
    print(header)
    for index, row in enumerate(rows, 1):
        category = row.get("category")
        suffix = f"  [{category}]" if category else ""
        print(f"  {index}. {row.get('behavior')}{suffix}")
    if categories and not args.category:
        print(f"categories: {', '.join(categories)}")
    return 0
