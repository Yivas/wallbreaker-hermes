import json
import re
import tarfile
import tomllib
from pathlib import Path

import pytest
import yaml

from scripts.check_release_artifacts import (
    SETUP_FILES,
    VERSION,
    check_sdist,
    check_source_versions,
)

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
SETUP = INTEGRATION / "skills" / "wallbreaker-campaign-setup"


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
        "Before any live command, use `clarify`",
        "Confirmation that strict cleanup and review evidence are required.",
        "plan.validated",
        "If any input changes,",
        "Never invoke `--show-evidence`",
        "Do not declare success unless verification exits `0`.",
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


def test_skill_requires_coordinator_capabilities_not_a_release():
    text = SKILL.read_text(encoding="utf-8")
    requirements = text.split("## Coordinator requirements\n", 1)[1].split(
        "## Required checks\n", 1
    )[0]

    assert "not pinned to the target release" in requirements
    assert "discover and load this skill" in requirements
    assert "native `clarify`" in requirements
    assert "normal `terminal` tool" in requirements
    assert "installed `wallbreaker` CLI" in requirements
    assert "If a required capability is missing, stop" in requirements
    assert "do not set up a second bot or conversation account" in requirements
    assert "do not copy the coordinator's credentials" in requirements
    assert HERMES_BASELINE_RELEASE not in requirements
    assert HERMES_BASELINE_VERSION not in requirements
    assert HERMES_BASELINE_SHA not in requirements
    assert "operator-side Hermes Agent release is" not in text


def test_skill_keeps_the_exact_target_baseline():
    text = SKILL.read_text(encoding="utf-8")
    target_check = text.split("## Procedure\n", 1)[1].split("2. Use", 1)[0]

    assert HERMES_BASELINE_RELEASE == "v2026.8.13"
    assert HERMES_BASELINE_VERSION == "0.20.1"
    assert HERMES_BASELINE_SHA == "f80f453ae0679347e38abc917c7f94f717bf96c5"
    assert "separate target checkout remains pinned" in target_check
    for baseline in (
        HERMES_BASELINE_RELEASE,
        HERMES_BASELINE_VERSION,
        HERMES_BASELINE_SHA,
    ):
        assert baseline in target_check
    assert "Never use the coordinator's checkout or home as the target" in target_check


@pytest.mark.parametrize("name", ["wallbreaker-hermes", "wallbreaker-campaign-setup"])
def test_companion_skills_have_public_metadata(name):
    text = (INTEGRATION / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    metadata = _frontmatter(text)
    assert metadata["name"] == name
    assert metadata["description"].endswith(".")
    assert len(metadata["description"]) <= 60
    assert metadata["version"] == VERSION
    assert metadata["license"] == "AGPL-3.0-or-later"
    assert metadata["platforms"] == ["linux", "macos", "windows"]
    assert metadata["metadata"]["hermes"]["related_skills"] == [
        "wallbreaker-campaign-setup" if name == "wallbreaker-hermes" else "wallbreaker-hermes"
    ]


def test_setup_references_are_bundled_and_self_contained():
    assert {path.relative_to(SETUP).as_posix() for path in SETUP.rglob("*") if path.is_file()} == {
        "SKILL.md", *SETUP_FILES
    }
    text = (SETUP / "SKILL.md").read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)]+)\)", text)
    assert set(links) == set(SETUP_FILES)
    for link in links:
        target = (SETUP / link).resolve()
        assert target.is_relative_to(SETUP.resolve())
        assert target.is_file()


def test_skills_keep_measurement_and_authorization_boundaries():
    operator = " ".join(SKILL.read_text(encoding="utf-8").split())
    setup = " ".join((SETUP / "SKILL.md").read_text(encoding="utf-8").split())
    diagnosis = " ".join(
        (SETUP / "references/diagnosing-harness-failures.md").read_text(encoding="utf-8").split()
    )
    for required in (
        "Reuse decisions already supplied", "once per unchanged plan",
        "Do not relabel expectations", "HMAC binds private evidence; it does not encrypt",
        "not absence of security findings or judge accuracy",
    ):
        assert required in operator
    for required in (
        "before proposing models, paid probes, or a benchmark",
        "offline structural verification does not require that key",
        "does not test model availability", "files byte-identical",
    ):
        assert required in setup
    for required in (
        "Parser acceptance is not strict schema validation or semantic accuracy",
        "Evidence awaiting review is not evidence known to be absent",
        "Preserve reports, evidence, and locks",
    ):
        assert required in diagnosis


def test_setup_templates_reuse_public_fictional_contracts():
    suite_path = SETUP / "templates/lab-suite.yaml"
    suite = load_suite(suite_path)
    assert len(suite.cases) == 3
    assert suite_path.read_text(encoding="utf-8") == (
        INTEGRATION / "examples/synthetic-suite.yaml"
    ).read_text(encoding="utf-8")
    manifest = json.loads((SETUP / "templates/lab-manifest.json").read_text(encoding="utf-8"))
    assert manifest == json.loads((INTEGRATION / "examples/clean-manifest.json").read_text(encoding="utf-8"))
    config = tomllib.loads((SETUP / "templates/lab-config.toml").read_text(encoding="utf-8"))
    assert config["target"]["protocol"] == "hermes-lab"
    assert config["target"]["model"] == manifest["model"]
    assert config["target"]["hermes_provider"] == manifest["provider"]
    assert manifest["expected_tool_count"] == 0
    assert config["profiles"][config["default_profile"]]["base_url"] == "https://api.example.invalid/v1"
    assert "api_key" not in config["target"]


def test_release_versions_include_both_skills_and_dashboard_lock():
    check_source_versions(ROOT)


def test_sdist_requires_setup_and_all_companions(tmp_path):
    archive = tmp_path / "empty.tar.gz"
    with tarfile.open(archive, "w:gz"):
        pass
    with pytest.raises(SystemExit) as error:
        check_sdist(archive)
    for name in ("SKILL.md", *SETUP_FILES):
        assert f"integrations/hermes/skills/wallbreaker-campaign-setup/{name}" in str(error.value)


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
        "D:/Hermes",
        "operator-home",
        "Local installation adaptation",
        "HERMES_HOME=",
        "api_key =",
        "sk-",
        "github_pat_",
        "BEGIN PRIVATE KEY",
    ):
        assert blocked not in text
