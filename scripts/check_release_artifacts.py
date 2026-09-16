from __future__ import annotations

import json
import re
import sys
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path


DISTRIBUTION = "wallbreaker-hermes"
VERSION = "0.7.1"
WHEEL_PREFIX = f"wallbreaker_hermes-{VERSION}-"
SDIST_NAME = f"wallbreaker_hermes-{VERSION}.tar.gz"
HERMES_SKILLS = ("wallbreaker-hermes", "wallbreaker-campaign-setup")
SETUP_FILES = (
    "references/preparing-campaign-artifacts.md",
    "references/diagnosing-harness-failures.md",
    "templates/lab-suite.yaml",
    "templates/lab-config.toml",
    "templates/lab-manifest.json",
)
REQUIRED_WHEEL = {
    "wallbreaker/__init__.py",
    "wallbreaker/tui/app.tcss",
    "wallbreaker/dashboard/web/dist/index.html",
}
FORBIDDEN_PARTS = {
    ".env",
    ".git",
    ".venv",
    "library",
    "node_modules",
    "sessions",
    "wb_runs",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def wheel_metadata(archive: zipfile.ZipFile) -> dict[str, str]:
    names = archive.namelist()
    metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
    if len(metadata_paths) != 1:
        fail("wheel must contain exactly one METADATA file")
    message = BytesParser().parsebytes(archive.read(metadata_paths[0]))
    return dict(message.items())


def check_forbidden(names: list[str]) -> None:
    for name in names:
        path = Path(name)
        parts = set(path.parts)
        basename = path.name.lower()
        if (
            parts & FORBIDDEN_PARTS
            or basename.startswith(".env")
            or basename.endswith(".env")
            or name.endswith((".map", ".sqlite3"))
        ):
            fail(f"blocked release path: {name}")


def check_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata = wheel_metadata(archive)
        if metadata.get("Name") != DISTRIBUTION or metadata.get("Version") != VERSION:
            fail("wheel metadata name or version is incorrect")
        if metadata.get("Requires-Python") != ">=3.11":
            fail("wheel Requires-Python is incorrect")
        if metadata.get("License-Expression") != "AGPL-3.0-or-later":
            fail("wheel license expression is incorrect")
        missing = REQUIRED_WHEEL - set(names)
        if missing:
            fail(f"wheel is missing: {', '.join(sorted(missing))}")
        if any(name.startswith("integrations/hermes/") for name in names):
            fail("Hermes skills must remain source-distributed, not wheel contents")
        if any(name.startswith("wallbreaker_hermes/") for name in names):
            fail("wheel must preserve the wallbreaker import package")
        if any(
            name.startswith("wallbreaker/dashboard/web/src/")
            or "/__tests__/" in name
            or "/tests/" in name
            for name in names
        ):
            fail("wheel contains development-only sources or tests")
        entry_points = archive.read(
            next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
        ).decode("utf-8")
        for expected in (
            "wallbreaker = wallbreaker.cli:main",
            "wb = wallbreaker.cli:main",
            "p4rs3lt0ngv3-mcp = p4rs3lt0ngv3_mcp.server:main",
        ):
            if expected not in entry_points:
                fail(f"wheel entry point is missing: {expected}")
        index = archive.read("wallbreaker/dashboard/web/dist/index.html").decode("utf-8")
        for reference in re.findall(r'(?:src|href)="([^"]+)"', index):
            if reference.startswith(("http://", "https://")):
                fail("dashboard release cannot reference remote assets")
            asset = "wallbreaker/dashboard/web/dist/" + reference.lstrip("/")
            if asset not in names:
                fail(f"dashboard asset is missing: {asset}")
        check_forbidden(names)


def check_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        names = archive.getnames()
        root = f"wallbreaker_hermes-{VERSION}/"
        required = {
            root + "CHANGELOG.md",
            root + "LICENSE",
            root + "NOTICE",
            root + "config.example.toml",
            root + "library.lock.toml",
            root + "wallbreaker/dashboard/web/dist/index.html",
            root + "wallbreaker/dashboard/web/package.json",
            root + "wallbreaker/dashboard/web/package-lock.json",
            root + "wallbreaker/dashboard/web/bun.lock",
            root + "wallbreaker/tui/app.tcss",
        }
        required.update(
            root + f"integrations/hermes/skills/{name}/SKILL.md"
            for name in HERMES_SKILLS
        )
        required.update(
            root + "integrations/hermes/skills/wallbreaker-campaign-setup/" + name
            for name in SETUP_FILES
        )
        missing = required - set(names)
        if missing:
            fail(f"sdist is missing: {', '.join(sorted(missing))}")
        check_forbidden(names)


def check_source_versions(root: Path) -> None:
    package = json.loads(
        (root / "wallbreaker/dashboard/web/package.json").read_text(encoding="utf-8")
    )
    package_lock = json.loads(
        (root / "wallbreaker/dashboard/web/package-lock.json").read_text(encoding="utf-8")
    )
    init = (root / "wallbreaker/__init__.py").read_text(encoding="utf-8")
    if package["version"] != VERSION:
        fail("dashboard version is out of sync")
    if (
        package_lock["version"] != VERSION
        or package_lock["packages"][""]["version"] != VERSION
    ):
        fail("dashboard lock version is out of sync")
    if f'__version__ = "{VERSION}"' not in init:
        fail("Python version is out of sync")
    for name in HERMES_SKILLS:
        skill = (root / f"integrations/hermes/skills/{name}/SKILL.md").read_text(
            encoding="utf-8"
        )
        if f"version: {VERSION}" not in skill:
            fail(f"{name} skill version is out of sync")


def main() -> None:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    wheels = sorted(dist.glob(WHEEL_PREFIX + "*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or [path.name for path in sdists] != [SDIST_NAME]:
        fail("dist must contain exactly the Wallbreaker Hermes wheel and sdist")
    check_wheel(wheels[0])
    check_sdist(sdists[0])
    check_source_versions(Path(__file__).resolve().parents[1])
    print(f"verified {wheels[0].name} and {sdists[0].name}")


if __name__ == "__main__":
    main()
