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

    Bundled names win, so a stray file called like one of them cannot silently replace the
    reference battery. A local battery is addressed as ``file:/path/to/battery.yaml`` or by giving
    an existing path directly; the file format and its optional digest pin are documented by
    ``wallbreaker.datasets.local``, which ships no content.
    """
    raw = source or "harmbench"
    key = raw.lower()
    if key in DATASETS:
        return DATASETS[key]
    candidate = raw[5:] if key.startswith("file:") else raw
    path = Path(candidate)
    if path.is_file() or path.exists():
        return LocalBatteryLoader(path)
    raise KeyError(
        f"unknown dataset '{source}'. Known sources: {', '.join(sources())}; "
        "a local battery can be passed as file:PATH"
    )


def load(source: str | None = "harmbench") -> list[dict]:
    return get(source).load()


def languages(source: str | None = "harmbench") -> list[str]:
    """Languages a battery declares. Only a local battery can declare them."""
    loader = get(source)
    if not hasattr(loader, "languages"):
        raise KeyError(f"source '{source}' does not declare languages")
    return loader.languages()


def categories(source: str | None = "harmbench") -> list[str]:
    return get(source).categories()


def sample(
    source: str | None = "harmbench",
    category=None,
    n: int = 8,
    seed: int = 0,
    language: str | None = None,
) -> list[dict]:
    loader = get(source)
    if language is None:
        return loader.sample(category, n, seed)
    if not hasattr(loader, "languages"):
        raise KeyError(f"source '{source}' does not support a language filter")
    return loader.sample(category, n, seed, language=language)


async def battery(
    source: str | None = "harmbench",
    category=None,
    n: int = 8,
    seed: int = 0,
    language: str | None = None,
) -> list[str] | None:
    loader = get(source)
    if language is None:
        return await loader.battery(category, n, seed)
    if not hasattr(loader, "languages"):
        raise KeyError(f"source '{source}' does not support a language filter")
    return await loader.battery(category, n, seed, language=language)


__all__ = [
    "DATASETS",
    "LocalBatteryLoader",
    "sources",
    "get",
    "load",
    "categories",
    "languages",
    "sample",
    "battery",
]
