from __future__ import annotations

import runpy
from pathlib import Path

import pytest


CHECK_RELEASE = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/check_release_artifacts.py")
)


@pytest.mark.parametrize(
    "name",
    (
        "package/.env",
        "package/.env.local",
        "package/.envrc",
        "package/config/.op.env",
    ),
)
def test_release_checker_rejects_dotenv_variants(name):
    with pytest.raises(SystemExit, match="blocked release path"):
        CHECK_RELEASE["check_forbidden"]([name])
