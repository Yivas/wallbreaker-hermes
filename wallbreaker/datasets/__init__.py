from __future__ import annotations

from pathlib import Path

from .advbench import AdvBenchLoader
from .harmbench import HarmBenchLoader
from .jbb import JBBLoader
from .local import LocalBatteryLoader
from .strongreject import StrongRejectLoader

DATASETS = {
    "harmbench": HarmBenchLoader(),
    "jbb": JBBLoader(),
    "strongreject": StrongRejectLoader(),
    "advbench": AdvBenchLoader(),
}


def sources() -> list[str]:
    return sorted(DATASETS)


def get(source: str | None = "harmbench"):
    """Resolve a battery source: a bundled name or a local file.

    A local battery is addressed as ``file:/path/to/battery.yaml`` or by giving an existing
    path directly. The file format and its optional digest pin are documented by
    ``wallbreaker.datasets.local``; the harness bundles no content for it.
    """
    raw = source or "harmbench"
    candidate = raw[5:] if raw.lower().startswith("file:") else raw
    path = Path(candidate)
    if candidate != "harmbench" and path.is_file():
        return LocalBatteryLoader(path)
    loader = DATASETS.get(raw.lower())
    if loader is None:
        raise KeyError(
            f"unknown dataset '{source}'. Known sources: {', '.join(sources())}; "
            "a local battery can be passed as file:PATH"
        )
    return loader


def load(source: str | None = "harmbench") -> list[dict]:
    return get(source).load()


def categories(source: str | None = "harmbench") -> list[str]:
    return get(source).categories()


def sample(source: str | None = "harmbench", category=None, n: int = 8, seed: int = 0) -> list[dict]:
    return get(source).sample(category, n, seed)


async def battery(source: str | None = "harmbench", category=None, n: int = 8, seed: int = 0) -> list[str] | None:
    return await get(source).battery(category, n, seed)


__all__ = [
    "DATASETS",
    "LocalBatteryLoader",
    "sources",
    "get",
    "load",
    "categories",
    "sample",
    "battery",
]
