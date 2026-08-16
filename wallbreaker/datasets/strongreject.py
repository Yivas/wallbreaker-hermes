from __future__ import annotations

from ._common import BaseLoader

DATASET_URL = (
    "https://raw.githubusercontent.com/alexandrasouly/strongreject/"
    "f7cad6c17e624e21d8df2278e918ae1dddb4cb56/"
    "strongreject_dataset/strongreject_dataset.csv"
)
DATASET_SHA256 = "4dd70357e4ff8b5d0ba5ebafecab5d6dd5633ce8046e3dd1c8bd93e64de44381"


class StrongRejectLoader(BaseLoader):
    name = "strongreject"
    url = DATASET_URL
    sha256 = DATASET_SHA256
    cache_filename = "strongreject_dataset.csv"
    benign = False

    def normalize(self, row: dict, idx: int, benign: bool) -> dict | None:
        behavior = (row.get("forbidden_prompt") or "").strip()
        if not behavior:
            return None
        category = (row.get("category") or "strongreject").strip() or "strongreject"
        return {
            "id": f"strongreject-{idx}",
            "behavior": behavior,
            "category": category,
            "source": self.name,
            "benign": benign,
        }
