"""Batteries supplied by the operator as a local file.

The harness ships only standard reference batteries. Anything the operator writes stays local: this
loader reads a file, validates it against a closed schema, and can pin it to a digest so a later run
fails closed if the file changed.

Format (YAML or JSON)::

    schema: wallbreaker.local-battery/v1
    id: my-battery
    language: es            # optional; the label is informational
    items:
      - id: item-1
        category: cybercrime_intrusion
        behavior: "..."     # one objective per item

If ``<path>.sha256`` exists next to the file, its hex digest must match the file or the load is
refused. That is the optional pin for a battery you keep outside version control.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

import yaml

SCHEMA = "wallbreaker.local-battery/v1"
MAX_ITEMS = 500
MAX_BEHAVIOR_CHARS = 8192
MAX_FILE_BYTES = 1_048_576
_ID = re.compile(r"^[a-z0-9]([a-z0-9._-]{0,62}[a-z0-9])?$")


class LocalBatteryError(ValueError):
    """The operator-supplied battery is unusable."""


def _read_document(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise LocalBatteryError(f"cannot read battery: {exc}") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise LocalBatteryError(f"battery is larger than {MAX_FILE_BYTES} bytes")
    pin = path.with_name(path.name + ".sha256")
    if pin.is_file():
        expected = pin.read_text(encoding="utf-8").strip().split()[0].lower()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise LocalBatteryError(f"battery does not match its {pin.name} pin")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LocalBatteryError("battery is not valid UTF-8") from exc
    try:
        if path.suffix.lower() in {".json", ".jsonl"}:
            if path.suffix.lower() == ".jsonl":
                document = {
                    "schema": SCHEMA,
                    "id": path.stem,
                    "items": [json.loads(line) for line in text.splitlines() if line.strip()],
                }
            else:
                document = json.loads(text)
        else:
            document = yaml.safe_load(text)
    except (ValueError, yaml.YAMLError) as exc:
        raise LocalBatteryError(f"battery is not valid YAML or JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise LocalBatteryError("battery must be a mapping")
    return document


def validate_battery(document: dict, *, source: str = "<memory>") -> list[dict]:
    extra = set(document) - {"schema", "id", "language", "items"}
    if extra:
        raise LocalBatteryError(f"unexpected keys in {source}: {', '.join(sorted(extra))}")
    if document.get("schema") != SCHEMA:
        raise LocalBatteryError(f"battery schema must be {SCHEMA}")
    identifier = document.get("id")
    if not isinstance(identifier, str) or not _ID.match(identifier):
        raise LocalBatteryError("battery id must be a short lowercase slug")
    language = document.get("language")
    if language is not None and not (isinstance(language, str) and 0 < len(language) <= 16):
        raise LocalBatteryError("battery language must be a short string when present")
    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise LocalBatteryError("battery needs a non-empty items list")
    if len(items) > MAX_ITEMS:
        raise LocalBatteryError(f"battery has more than {MAX_ITEMS} items")

    seen: set[str] = set()
    rows: list[dict] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise LocalBatteryError(f"item {index} must be a mapping")
        unknown = set(item) - {"id", "category", "behavior", "language"}
        if unknown:
            raise LocalBatteryError(
                f"item {index} has unexpected keys: {', '.join(sorted(unknown))}"
            )
        item_id = item.get("id")
        category = item.get("category")
        behavior = item.get("behavior")
        if not isinstance(item_id, str) or not _ID.match(item_id):
            raise LocalBatteryError(f"item {index} needs a short lowercase id")
        if item_id in seen:
            raise LocalBatteryError(f"duplicate item id: {item_id}")
        seen.add(item_id)
        if not isinstance(category, str) or not category.strip():
            raise LocalBatteryError(f"item {item_id} needs a category")
        if not isinstance(behavior, str) or not behavior.strip():
            raise LocalBatteryError(f"item {item_id} needs a behavior")
        if len(behavior) > MAX_BEHAVIOR_CHARS:
            raise LocalBatteryError(
                f"item {item_id} is longer than {MAX_BEHAVIOR_CHARS} characters"
            )
        item_language = item.get("language", language)
        if item_language is not None and not (
            isinstance(item_language, str) and 0 < len(item_language.strip()) <= 16
        ):
            raise LocalBatteryError(f"item {item_id} language must be a short string when present")
        rows.append(
            {
                "id": item_id,
                "category": category.strip(),
                "behavior": behavior.strip(),
                "source": document.get("id"),
                "language": item_language.strip() if isinstance(item_language, str) else None,
            }
        )
    return rows


class LocalBatteryLoader:
    """A battery read from one operator file; the harness ships no content for it."""

    name = "local"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[dict]:
        return validate_battery(_read_document(self.path), source=str(self.path))

    def categories(self) -> list[str]:
        return sorted({row["category"] for row in self.load()})

    def languages(self) -> list[str]:
        """Every language label the battery declares, so a comparison can be split by language."""
        found = {row["language"] for row in self.load() if row["language"]}
        return sorted(found)

    def sample(
        self, category=None, n: int = 8, seed: int = 0, language: str | None = None
    ) -> list[dict]:
        rows = self.load()
        rng = random.Random(seed)
        if category:
            rows = [row for row in rows if row["category"] == category]
        if language is not None:
            rows = [row for row in rows if row["language"] == language]
        rng.shuffle(rows)
        return rows[:n]

    async def battery(
        self, category=None, n: int = 8, seed: int = 0, language: str | None = None
    ) -> list[str]:
        return [row["behavior"] for row in self.sample(category, n, seed, language=language)]
