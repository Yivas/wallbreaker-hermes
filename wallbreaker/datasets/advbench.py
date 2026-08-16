from __future__ import annotations

from ._common import BaseLoader

DATASET_URL = (
    "https://raw.githubusercontent.com/llm-attacks/llm-attacks/"
    "098262edf85f807224e70ecd87b9d83716bf6b73/"
    "data/advbench/harmful_behaviors.csv"
)
DATASET_SHA256 = "6cd1a5c63c07610d7eb67307772ee5606017ee950b5770ab288a2c487489d3e1"


class AdvBenchLoader(BaseLoader):
    name = "advbench"
    url = DATASET_URL
    sha256 = DATASET_SHA256
    cache_filename = "advbench_harmful_behaviors.csv"
    benign = False

    def normalize(self, row: dict, idx: int, benign: bool) -> dict | None:
        behavior = (row.get("goal") or "").strip()
        if not behavior:
            return None
        out = {
            "id": f"advbench-{idx}",
            "behavior": behavior,
            "category": "advbench",
            "source": self.name,
            "benign": benign,
        }
        target = (row.get("target") or "").strip()
        if target:
            out["prefill"] = target
        return out
