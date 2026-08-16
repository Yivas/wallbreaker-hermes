from __future__ import annotations

from ._common import BaseLoader

HARMFUL_URL = (
    "https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors/resolve/"
    "886acc352a31533ffbcf4ef22c744658688086fc/data/harmful-behaviors.csv"
)
BENIGN_URL = (
    "https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors/resolve/"
    "886acc352a31533ffbcf4ef22c744658688086fc/data/benign-behaviors.csv"
)
HARMFUL_SHA256 = "4a8ec6832056b631eb092dccc60d37a61c3d441268268888b3d006288afeffa1"
BENIGN_SHA256 = "3cda234d21a991fa309bbfea4b6d9dae31ccdf8e9d452424b6a983e4fdc33468"


class JBBLoader(BaseLoader):
    name = "jbb"
    url = HARMFUL_URL
    sha256 = HARMFUL_SHA256
    cache_filename = "jbb_behaviors.csv"
    benign = False
    extra_sources = ((BENIGN_URL, "jbb_benign_behaviors.csv", True, BENIGN_SHA256),)

    def normalize(self, row: dict, idx: int, benign: bool) -> dict | None:
        goal = (row.get("Goal") or row.get("Behavior") or row.get("Prompt") or "").strip()
        if not goal:
            return None
        category = (row.get("Category") or "jbb").strip() or "jbb"
        rid = (row.get("Index") or row.get("Behavior") or "").strip() or f"jbb-{idx}"
        return {
            "id": rid,
            "behavior": goal,
            "category": category,
            "source": self.name,
            "benign": benign,
        }
