"""The battery subcommand reads bundled batteries and operator files from a plain command line."""

from __future__ import annotations

import json

import pytest

from wallbreaker import battery_cli
from wallbreaker.datasets.local import LocalBatteryLoader


class _FakeLoader:
    """Bundled loaders fetch asynchronously; the fake mirrors that so the bug cannot come back."""

    def __init__(self, rows, error=None):
        self._rows = rows
        self._error = error
        self.ensured = 0

    async def ensure(self):
        self.ensured += 1
        return self._error

    def categories(self):
        return sorted({row["category"] for row in self._rows})

    def sample(self, category=None, n=8, seed=0):
        rows = [row for row in self._rows if category is None or row["category"] == category]
        return rows[:n]


def _args(source="jbb", category=None, n=2, seed=0, as_json=False):
    return type(
        "Args",
        (),
        {"source": source, "category": category, "n": n, "seed": seed, "json": as_json},
    )()


@pytest.fixture
def rows():
    return [
        {"id": "a", "behavior": "First behavior", "category": "alpha", "benign": False},
        {"id": "b", "behavior": "Second behavior", "category": "beta", "benign": True},
        {"id": "c", "behavior": "Third behavior", "category": "alpha", "benign": False},
    ]


def test_lists_sampled_behaviors(monkeypatch, capsys, rows):
    loader = _FakeLoader(rows)
    monkeypatch.setattr(battery_cli.datasets, "get", lambda source: loader)

    assert battery_cli.run_battery_cli(_args()) == 0
    out = capsys.readouterr().out
    assert "2 behaviors from jbb" in out
    assert "First behavior" in out and "Second behavior" in out
    assert loader.ensured == 1


def test_json_output_is_machine_readable(monkeypatch, capsys, rows):
    monkeypatch.setattr(battery_cli.datasets, "get", lambda source: _FakeLoader(rows))

    assert battery_cli.run_battery_cli(_args(category="alpha", as_json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "wallbreaker.battery-sample/v1"
    assert payload["count"] == 2
    assert [item["id"] for item in payload["behaviors"]] == ["a", "c"]


def test_unknown_source_lists_valid_ones(monkeypatch, capsys):
    def explode(source):
        raise KeyError("unknown dataset 'nope'. Known sources: advbench, harmbench, jbb")

    monkeypatch.setattr(battery_cli.datasets, "get", explode)

    assert battery_cli.run_battery_cli(_args(source="nope")) == 2
    assert "advbench" in capsys.readouterr().err


def test_unknown_category_is_a_usage_error(monkeypatch, capsys, rows):
    monkeypatch.setattr(battery_cli.datasets, "get", lambda source: _FakeLoader(rows))

    assert battery_cli.run_battery_cli(_args(category="missing")) == 2
    assert "No behaviors for category" in capsys.readouterr().err


def test_download_failure_is_reported(monkeypatch, capsys, rows):
    monkeypatch.setattr(
        battery_cli.datasets, "get", lambda source: _FakeLoader(rows, error="HTTP 503")
    )

    assert battery_cli.run_battery_cli(_args()) == 1
    assert "HTTP 503" in capsys.readouterr().err


class _SyncLoader(_FakeLoader):
    """The local loader has no ensure at all."""

    ensure = None


def test_async_loader_is_awaited(monkeypatch, capsys, rows):
    monkeypatch.setattr(battery_cli.datasets, "get", lambda source: _FakeLoader(rows))

    assert battery_cli.run_battery_cli(_args()) == 0
    out = capsys.readouterr().out
    assert "First behavior" in out, "an un-awaited ensure() would leave the sample empty"


def test_loader_without_ensure_works(monkeypatch, capsys, rows):
    monkeypatch.setattr(battery_cli.datasets, "get", lambda source: _SyncLoader(rows))

    assert battery_cli.run_battery_cli(_args()) == 0
    assert "First behavior" in capsys.readouterr().out


def test_operator_battery_needs_no_network(tmp_path, capsys):
    path = tmp_path / "battery.json"
    path.write_text(
        json.dumps(
            {
                "schema": "wallbreaker.local-battery/v1",
                "id": "fixture",
                "language": "es",
                "items": [
                    {"id": "item-1", "category": "alpha", "behavior": "Synthetic one"},
                    {"id": "item-2", "category": "alpha", "behavior": "Synthetic two"},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert isinstance(battery_cli.datasets.get(f"file:{path}"), LocalBatteryLoader)

    assert battery_cli.run_battery_cli(_args(source=f"file:{path}", n=2)) == 0
    assert "Synthetic one" in capsys.readouterr().out


def test_cache_directory_survives_a_read_only_installation(tmp_path, monkeypatch):
    """A protected installation must still download: the cache moves to the user profile."""
    from wallbreaker.datasets import _common

    monkeypatch.delenv(_common.LIBRARY_DIR_ENV, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "win"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "nix"))
    monkeypatch.setattr(_common.os, "access", lambda path, mode: False)

    resolved = _common.library_dir()
    # Whichever per-user directory the platform uses, it must stay inside the profile and outside
    # the read-only package.
    assert resolved.is_relative_to(tmp_path)
    assert resolved.parent.name == "wallbreaker-hermes"


def test_profile_directory_prefers_the_windows_variable(tmp_path, monkeypatch):
    from wallbreaker.datasets import _common

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert _common.user_data_dir() == str(tmp_path / "wallbreaker-hermes")


def test_profile_directory_falls_back_to_xdg(tmp_path, monkeypatch):
    from wallbreaker.datasets import _common

    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert _common.user_data_dir() == str(tmp_path / "wallbreaker-hermes")


def test_explicit_cache_directory_wins(tmp_path, monkeypatch):
    from wallbreaker.datasets import _common

    monkeypatch.setenv(_common.LIBRARY_DIR_ENV, str(tmp_path / "custom"))
    assert _common.library_dir() == tmp_path / "custom"
