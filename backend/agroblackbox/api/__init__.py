"""Authenticated, PostgreSQL-backed ``/api/v1`` routes (ABB-05 accounts, ABB-06 cases,
ABB-14 registered papers and evidence claims)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from . import auth, cases, evidence
from .deps import STORAGE_UNAVAILABLE


async def _storage_unavailable(_: Request, __: Exception) -> JSONResponse:
    # Generic message only: driver errors can contain host names or credentials.
    return JSONResponse(status_code=503, content={"detail": STORAGE_UNAVAILABLE})


def include_api_v1(app: FastAPI) -> None:
    app.include_router(auth.router)
    app.include_router(cases.router)
    app.include_router(evidence.papers_router)
    app.include_router(evidence.claims_router)
    app.add_exception_handler(OperationalError, _storage_unavailable)
    app.add_exception_handler(InterfaceError, _storage_unavailable)
