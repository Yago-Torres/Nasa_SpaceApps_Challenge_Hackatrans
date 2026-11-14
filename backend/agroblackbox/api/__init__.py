"""Authenticated, PostgreSQL-backed ``/api/v1`` routes (ABB-05 accounts, ABB-06 cases,
ABB-10 case observations, timeline and hypotheses, ABB-14 registered papers and evidence claims,
ABB-15 claim disagreements and study applicability, ABB-19 Uncertainty Hunter)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from . import auth, cases, comparability, evidence, hypotheses, observations, timeline, uncertainty
from .deps import STORAGE_UNAVAILABLE


async def _storage_unavailable(_: Request, __: Exception) -> JSONResponse:
    # Generic message only: driver errors can contain host names or credentials.
    return JSONResponse(status_code=503, content={"detail": STORAGE_UNAVAILABLE})


def include_api_v1(app: FastAPI) -> None:
    app.include_router(auth.router)
    app.include_router(cases.router)
    app.include_router(observations.router)
    app.include_router(timeline.router)
    app.include_router(hypotheses.router)
    app.include_router(hypotheses.catalog_router)
    app.include_router(evidence.papers_router)
    # ABB-15 before the claims router: "/claims/disagreements" must not match "/claims/{claim_id}".
    app.include_router(comparability.router)
    app.include_router(evidence.claims_router)
    app.include_router(uncertainty.router)
    app.include_router(uncertainty.catalog_router)
    app.add_exception_handler(OperationalError, _storage_unavailable)
    app.add_exception_handler(InterfaceError, _storage_unavailable)
