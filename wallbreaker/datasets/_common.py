from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import random
from pathlib import Path

import httpx

from .._fsutil import atomic_write_bytes


def library_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "library"


def cache_path(filename: str) -> Path:
    return library_dir() / filename


def _matches_digest(path: Path, expected_sha256: str) -> bool:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256
    except OSError:
        return False


def download(
    url: str,
    path: Path,
    expected_sha256: str,
    label: str = "dataset",
) -> str | None:
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        if resp.status_code != 200:
            return f"{label} download failed: HTTP {resp.status_code}"
        if hashlib.sha256(resp.content).hexdigest() != expected_sha256:
            return f"{label} download failed: integrity mismatch"
        atomic_write_bytes(path, resp.content)
        return None
    except (httpx.HTTPError, OSError) as exc:
        return f"{label} download failed: {exc}"


def parse_csv(text: str, mapper) -> list[dict]:
    rows: list[dict] = []
    reader = csv.DictReader(io.StringIO(text))
    for idx, raw in enumerate(reader):
        clean = {(k or "").strip(): (v or "") for k, v in raw.items()}
        norm = mapper(clean, idx)
        if norm and norm.get("behavior"):
            rows.append(norm)
    return rows


def stratified_sample(behaviors: list[dict], category=None, n: int = 8, seed: int = 0) -> list[dict]:
    if not behaviors:
        return []
    rng = random.Random(seed)
    if category:
        pool = [b for b in behaviors if b["category"] == category]
        rng.shuffle(pool)
        return pool[:n]
    by_cat: dict[str, list] = {}
    for b in behaviors:
        by_cat.setdefault(b["category"], []).append(b)
    for lst in by_cat.values():
        rng.shuffle(lst)
    out: list[dict] = []
    cats = sorted(by_cat)
    rng.shuffle(cats)
    i = 0
    while len(out) < n and any(by_cat[c] for c in cats):
        c = cats[i % len(cats)]
        if by_cat[c]:
            out.append(by_cat[c].pop())
        i += 1
    return out[:n]


class BaseLoader:
    name = ""
    url = ""
    sha256 = ""
    cache_filename = ""
    benign = False
    extra_sources: tuple = ()

    def _sources(self):
        yield (self.url, self.cache_filename, self.benign, self.sha256)
        for src in self.extra_sources:
            yield src

    def cache_path(self) -> Path:
        return cache_path(self.cache_filename)

    def is_cached(self) -> bool:
        return all(
            _matches_digest(cache_path(filename), expected_sha256)
            for _url, filename, _benign, expected_sha256 in self._sources()
        )

    def normalize(self, row: dict, idx: int, benign: bool) -> dict | None:
        raise NotImplementedError

    def _ensure_blocking(self) -> str | None:
        for url, filename, _benign, expected_sha256 in self._sources():
            path = cache_path(filename)
            if path.exists():
                if not _matches_digest(path, expected_sha256):
                    return f"{self.name} cache failed integrity verification"
                continue
            err = download(url, path, expected_sha256, label=self.name)
            if err:
                return err
        return None

    async def ensure(self, offline: bool = False) -> str | None:
        if self.is_cached():
            return None
        if any(
            cache_path(filename).exists()
            and not _matches_digest(cache_path(filename), expected_sha256)
            for _url, filename, _benign, expected_sha256 in self._sources()
        ):
            return f"{self.name} cache failed integrity verification"
        if offline:
            return f"{self.name} not cached and offline."
        return await asyncio.to_thread(self._ensure_blocking)

    def load(self) -> list[dict]:
        rows: list[dict] = []
        for _url, filename, benign, expected_sha256 in self._sources():
            path = cache_path(filename)
            if not _matches_digest(path, expected_sha256):
                continue
            text = path.read_text(encoding="utf-8")
            for norm in parse_csv(text, lambda r, i, b=benign: self.normalize(r, i, b)):
                norm.setdefault("source", self.name)
                rows.append(norm)
        return rows

    def categories(self) -> list[str]:
        return sorted({b["category"] for b in self.load()})

    def sample(self, category=None, n: int = 8, seed: int = 0) -> list[dict]:
        return stratified_sample(self.load(), category, n, seed)

    async def battery(self, category=None, n: int = 8, seed: int = 0) -> list[str] | None:
        err = await self.ensure()
        if err or not self.is_cached():
            return None
        rows = self.sample(category, n, seed)
        if not rows:
            return None
        return [b["behavior"] for b in rows]
