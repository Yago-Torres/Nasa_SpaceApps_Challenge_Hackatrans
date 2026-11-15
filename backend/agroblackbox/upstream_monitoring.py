"""Counts calls to external sources for /api/metrics and logs their failures (ABB-30).

The wrappers are applied here, at application start, instead of decorating the service functions,
so the services (also reworked by ABB-27) stay unchanged. Every caller looks these functions up on
their module at call time (``power.fetch_power``, ``lit.lookup_paper``, ``verify_doi`` inside the
literature module, ``literature.search_literature`` in app.py), so the wrapped versions are used.
"""
from __future__ import annotations

from .observability import track_upstream
from .services import gpm, hls, literature, power

_WRAPPED = "_cropstory_monitored"


def _wrap(module, name: str, source: str, classify=None) -> None:
    fn = getattr(module, name)
    if getattr(fn, _WRAPPED, False):
        return
    wrapped = track_upstream(source, classify)(fn)
    setattr(wrapped, _WRAPPED, True)
    setattr(module, name, wrapped)


def install() -> None:
    """Idempotent."""
    _wrap(power, "fetch_power", "nasa_power", lambda record: "cache" if record.served_from_cache else "ok")
    _wrap(hls, "fetch_hls_series", "nasa_hls", lambda series: "cache" if series.requests == 0 else "ok")
    _wrap(gpm, "fetch_gpm_year", "nasa_gpm", lambda series: "cache" if series.requests == 0 else "ok")
    _wrap(literature, "search_literature", "openalex_search")
    _wrap(literature, "lookup_paper", "openalex_lookup")
    _wrap(literature, "verify_doi", "crossref",
          lambda check: {"VERIFIED_CROSSREF": "ok", "NOT_FOUND_IN_CROSSREF": "not_found"}.get(check.status, "error:unavailable"))


install()
