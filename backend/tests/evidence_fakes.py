"""Offline OpenAlex/Crossref stand-ins for ABB-14 tests (httpx.MockTransport).

Payload shapes mirror the real APIs; titles/DOIs of the three pilot papers are used as test data
only, all other values (authors, ORCIDs, years for synthetic works) are SYNTHETIC.
"""
from __future__ import annotations

import httpx

from agroblackbox.evidence_seed import PILOT_SEED
from agroblackbox.services import literature as lit

CC_BY_CROSSREF = "https://creativecommons.org/licenses/by/4.0"


def oa_work(wid: str, title: str, doi: str | None, *, year: int = 2022, license_: str | None = "cc-by") -> dict:
    return {
        "id": f"https://openalex.org/{wid}", "doi": f"https://doi.org/{doi}" if doi else None, "title": title,
        "display_name": title, "publication_year": year, "type": "article",
        "authorships": [{"author": {"display_name": "Synthetic Author", "orcid": None}}],
        "primary_location": {"license": license_, "landing_page_url": "https://example.org/landing",
                             "source": {"display_name": "Synthetic Journal"}},
        "open_access": {"is_oa": license_ is not None},
    }


def crossref_reply(doi: str, title: str, *, year: int = 2022, licensed: bool = True) -> httpx.Response:
    message = {
        "DOI": doi.upper(), "title": [title], "container-title": ["Synthetic Journal"],
        "issued": {"date-parts": [[year, 1, 1]]}, "type": "journal-article",
        "author": [{"given": "Ada", "family": "Synthetic", "ORCID": "https://orcid.org/0000-0000-0000-0000"}],
    }
    if licensed:
        message["license"] = [{"URL": CC_BY_CROSSREF, "content-version": "vor"}]
    return httpx.Response(200, json={"status": "ok", "message": message})


class FakeScholarly:
    """Answers single-work OpenAlex lookups and Crossref DOI checks; records every request."""

    def __init__(self, works: list[dict] = (), crossref: dict | None = None, openalex=None):
        self.by_doi = {lit.normalize_doi(w["doi"]): w for w in works if w.get("doi")}
        self.by_id = {w["id"].rsplit("/", 1)[1].upper(): w for w in works}
        self.crossref = dict(crossref or {})
        self.openalex = openalex  # optional override: Response or Exception for every OpenAlex call
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "api.openalex.org":
            if isinstance(self.openalex, Exception):
                raise self.openalex
            if self.openalex is not None:
                return self.openalex
            key = request.url.path.removeprefix("/works/")
            work = self.by_doi.get(key[4:].lower()) if key.lower().startswith("doi:") else self.by_id.get(key.upper())
            return httpx.Response(200, json=work) if work else httpx.Response(404, json={"error": "not found"})
        if request.url.host == "api.crossref.org":
            doi = request.url.path.removeprefix("/works/").lower()
            reply = self.crossref.get(doi, httpx.Response(404, text="Resource not found."))
            if isinstance(reply, Exception):
                raise reply
            return reply
        raise AssertionError(f"unexpected host {request.url.host}")

    def hosts(self, host: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == host]


def pilot_upstream(**overrides) -> FakeScholarly:
    """All three pilot papers resolvable and verified; ``overrides`` replaces Crossref replies by DOI."""
    works = [oa_work(f"W90{i}", entry["title"], entry["doi"]) for i, entry in enumerate(PILOT_SEED, start=1)]
    crossref = {entry["doi"]: crossref_reply(entry["doi"], entry["title"]) for entry in PILOT_SEED}
    crossref.update(overrides)
    return FakeScholarly(works, crossref)


def install(monkeypatch, fake: FakeScholarly) -> FakeScholarly:
    monkeypatch.setattr(lit, "_make_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    return fake
