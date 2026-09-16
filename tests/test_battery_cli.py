"""The battery subcommand reads bundled batteries and operator files from a plain command line."""

from __future__ import annotations

import json

import pytest

from wallbreaker import battery_cli
from wallbreaker.datasets.local import LocalBatteryLoader


class _FakeLoader:
    def __init__(self, rows, error=None):
        self._rows = rows
        self._error = error
        self.ensured = 0

    def ensure(self):
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
