import json
import re
from pathlib import Path

import yaml

from wallbreaker.hermes_campaign import load_suite
from wallbreaker.hermes_lab import (
    HERMES_BASELINE_RELEASE,
    HERMES_BASELINE_SHA,
    HERMES_BASELINE_VERSION,
    HERMES_MANIFEST_SCHEMA,
)


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "hermes"
SKILL = INTEGRATION / "skills" / "wallbreaker-hermes" / "SKILL.md"


def _frontmatter(text):
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None
    return yaml.safe_load(match.group(1))


def test_skill_is_discoverable_and_enforces_operator_gates():
    text = SKILL.read_text(encoding="utf-8")
    metadata = _frontmatter(text)

    assert metadata["name"] == "wallbreaker-hermes"
    assert metadata["description"].endswith(".")
    assert len(metadata["description"]) <= 60
    assert metadata["platforms"] == ["linux", "macos", "windows"]
    for required in (
        "clarify",
        "--dry-run",
        "--authorized --confirm TOKEN",
        "wallbreaker hermes review",
        "wallbreaker hermes verify",
        HERMES_BASELINE_RELEASE,
        HERMES_BASELINE_VERSION,
        HERMES_BASELINE_SHA,
    ):
        assert required in text
    assert "Never use `execute_code`" in text
    assert "install this skill into the clean Hermes checkout" in text


def test_fictional_examples_match_closed_schemas():
    suite = load_suite(INTEGRATION / "examples" / "synthetic-suite.yaml")
    assert len(suite.cases) == 3
    manifest = json.loads(
        (INTEGRATION / "examples" / "clean-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest == {
        "schema": HERMES_MANIFEST_SCHEMA,
        "mode": "clean",
        "provider": "fixture-provider",
        "model": "fixture/model",
        "files": [],
        "expected_tool_count": 0,
    }


def test_public_integration_contains_no_private_runtime_material():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in INTEGRATION.rglob("*")
        if path.is_file()
    )
    for blocked in (
        "D:\\Hermes",
        "HERMES_HOME=",
        "api_key =",
        "sk-",
        "github_pat_",
        "BEGIN PRIVATE KEY",
    ):
        assert blocked not in text
