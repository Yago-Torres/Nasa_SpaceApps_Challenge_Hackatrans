"""Generic on-disk TTL cache keyed by an opaque string (ABB-27).

``services.power`` already implements exactly this pattern for NASA POWER (see its
``_read_cache``/``_write_cache``); this module extracts the same, already-reviewed
approach into something ``services.literature`` can reuse for OpenAlex/Crossref
without touching the POWER module's tested cache code. A future cleanup could make
``services.power`` adopt this module too (tracked in CURRENT_STATE as follow-up, not
done in this change to avoid risking the existing NASA POWER cache tests).

A corrupt, expired, or otherwise unreadable entry is always treated as a cache miss,
never as an error: callers keep a working non-cached path. Writes are best-effort
(atomic rename, but a failure to write is logged and swallowed) because a cache
failure must never block a valid live answer.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_FORMAT = 1


@dataclass(frozen=True)
class CacheHit:
    raw: bytes
    retrieved_at: datetime
    age_seconds: float


def cache_key(parts: dict[str, Any]) -> str:
    """Stable key for a JSON-serializable dict of request-identifying parts."""
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _paths(directory: Path, key: str) -> tuple[Path, Path]:
    return directory / f'{key}.json', directory / f'{key}.meta.json'


def read_ttl_cache(directory: Path, key: str, ttl_seconds: float, now: datetime) -> CacheHit | None:
    data_path, meta_path = _paths(directory, key)
    try:
        if not (data_path.exists() and meta_path.exists()):
            return None
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        if meta.get('format') != CACHE_FORMAT:
            return None
        retrieved_at = datetime.fromisoformat(meta['retrieved_at'])
        if retrieved_at.tzinfo is None:
            return None
        age = (now - retrieved_at).total_seconds()
        if age < 0 or age >= ttl_seconds:
            return None
        raw = data_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != meta.get('sha256'):
            return None
        return CacheHit(raw=raw, retrieved_at=retrieved_at.astimezone(UTC), age_seconds=age)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def write_ttl_cache(directory: Path, key: str, raw: bytes, retrieved_at: datetime) -> None:
    data_path, meta_path = _paths(directory, key)
    sha = hashlib.sha256(raw).hexdigest()
    sidecar = json.dumps({'format': CACHE_FORMAT, 'sha256': sha, 'retrieved_at': retrieved_at.isoformat()})
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for path, content in ((data_path, raw), (meta_path, sidecar.encode())):
            tmp = path.with_name(path.name + '.tmp')
            tmp.write_bytes(content)
            os.replace(tmp, path)
    except OSError as e:  # a cache failure must not fail a valid live answer
        logger.warning('Could not write TTL cache entry under %s: %s', directory, type(e).__name__)
