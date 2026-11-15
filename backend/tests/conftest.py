"""Shared pytest fixtures for the whole backend test suite."""
from __future__ import annotations

import pytest

from agroblackbox.services import literature as lit


@pytest.fixture(autouse=True)
def _isolated_literature_cache(monkeypatch, tmp_path):
    """ABB-27: ``services.literature.search_literature`` now caches OpenAlex/Crossref
    search results on disk (``lookup_paper`` is deduplicated only, deliberately not
    cached - see services/literature.py). Every test in the suite gets its own empty
    cache directory, so tests never share state through the real
    ``backend/.cache/literature`` directory or through each other when they happen to
    search for the same query.
    """
    monkeypatch.setattr(lit, 'SEARCH_CACHE', tmp_path / 'literature-search-cache')
