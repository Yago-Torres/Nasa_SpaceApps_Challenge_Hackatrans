"""Operational telemetry for deployments (ABB-30): request ids, JSON logs, readiness and metrics.

Privacy rules (docs/operations/LEGAL_AND_DATA_POLICY.md, ADR-0004):
- Requests are logged and counted by their *route template* (``/api/v1/cases/{case_id}``), never by the
  raw URL: query strings (``/api/climate?latitude=…``) carry field coordinates.
- External-source events record the source, an outcome code and the request id. Never request URLs,
  parameters, coordinates, response bodies, API keys or contact addresses.
- Unhandled errors log the exception type and the code location only, not the message (driver and
  validation messages can contain user data).

Counters live in this process (one uvicorn worker in the deployment compose file); they reset on restart.
"""
from __future__ import annotations

import contextvars
import functools
import json
import logging
import os
import re
import threading
import time
import traceback
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, TypeVar

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("cropstory")
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_lock = threading.Lock()
_http_requests: Counter[tuple[str, str, str]] = Counter()
_http_seconds: Counter[str] = Counter()
_unhandled: Counter[str] = Counter()
_upstream: Counter[tuple[str, str]] = Counter()
_upstream_last_error: dict[str, tuple[float, str]] = {}
STARTED_AT = time.time()

T = TypeVar("T")


def app_version() -> str:
    """Release version baked into the image (APP_VERSION, e.g. the git tag), else the package version."""
    return os.getenv("APP_VERSION", "").strip() or "0.1.0"


# ── logging ──────────────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """One JSON object per line with the current request id; extra ``event`` fields are merged in."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        event = getattr(record, "event", None)
        if isinstance(event, dict):
            payload.update(event)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """JSON logs on stdout when LOG_FORMAT=json (the container default); plain text otherwise."""
    # httpx/httpcore log every request URL at INFO, including NASA POWER queries with the field's
    # latitude/longitude: keep them at WARNING in every environment.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    if os.getenv("LOG_FORMAT", "").lower() != "json":
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    # uvicorn's access log prints raw URLs (with coordinates in query strings): the middleware below
    # logs route templates instead, so the access logger is silenced.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True


# ── external sources ─────────────────────────────────────────────────────────

def record_upstream(source: str, outcome: str) -> None:
    """Count one call to an external source. Outcomes starting with ``error`` are failures."""
    with _lock:
        _upstream[(source, outcome)] += 1
        if outcome.startswith("error"):
            _upstream_last_error[source] = (time.time(), outcome)
    if outcome.startswith("error"):
        logger.warning("external source failed", extra={"event": {"event": "upstream_error", "source": source, "outcome": outcome}})


def _exception_outcome(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, str) and re.fullmatch(r"[a-z_]{1,40}", reason):
        return f"error:{reason}"
    name = type(exc).__name__
    if "NotFound" in name:
        return "not_found"
    if isinstance(exc, ValueError):
        return "invalid_input"
    return "error:unavailable"


def track_upstream(source: str, classify: Callable[[Any], str] | None = None):
    """Decorator for an async call to an external source: counts its outcome, then returns or re-raises."""
    def decorate(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                result = await fn(*args, **kwargs)
            except Exception as exc:
                record_upstream(source, _exception_outcome(exc))
                raise
            record_upstream(source, classify(result) if classify else "ok")
            return result
        return wrapper
    return decorate


# ── HTTP middleware ──────────────────────────────────────────────────────────

def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


async def request_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    incoming = request.headers.get("x-request-id", "")
    rid = incoming if _REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
    token = request_id_var.set(rid)
    started = time.perf_counter()
    status_code = 500
    try:
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:  # never leak details; the type and location are enough to find it
            frame = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
            where = f"{os.path.basename(frame.filename)}:{frame.lineno}" if frame else "unknown"
            with _lock:
                _unhandled[type(exc).__name__] += 1
            logger.error("unhandled error", extra={"event": {
                "event": "unhandled_error", "error_type": type(exc).__name__, "where": where,
                "route": _route_template(request), "method": request.method}})
            response = JSONResponse(status_code=500, content={"detail": "Internal error.", "request_id": rid})
        route = _route_template(request)
        elapsed = time.perf_counter() - started
        with _lock:
            _http_requests[(request.method, route, f"{status_code // 100}xx")] += 1
            _http_seconds[route] += elapsed
        if route not in ("/api/health", "/api/ready", "/api/metrics"):
            logger.info("request", extra={"event": {"event": "request", "method": request.method, "route": route,
                                                    "status": status_code, "duration_ms": round(elapsed * 1000, 1)}})
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        request_id_var.reset(token)


# ── readiness and metrics ────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def migration_head() -> str | None:
    """Head revision of the migrations shipped with this build (None if they are not packaged)."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    if not ini.exists():
        return None
    config = Config(str(ini))
    config.set_main_option("script_location", str(ini.parent / "migrations"))
    heads = ScriptDirectory.from_config(config).get_heads()
    return heads[0] if len(heads) == 1 else None


def readiness() -> tuple[bool, dict[str, str]]:
    """Database reachable and at the migration head of this build. Never returns connection details."""
    url = os.getenv("DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        return False, {"database": "not_configured"}
    from sqlalchemy import text

    from .api.deps import _factory_for

    try:
        with _factory_for(url)() as session:
            session.execute(text("SELECT 1"))
            current = session.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    except Exception as exc:  # report the class of failure only
        logger.warning("readiness check failed", extra={"event": {"event": "readiness_failed", "error_type": type(exc).__name__}})
        return False, {"database": "unreachable_or_not_migrated"}
    head = migration_head()
    if head is None:
        state = "unknown"
    elif current == [head]:
        state = "at_head"
    else:
        state = "not_at_head"
    return state == "at_head", {"database": "ok", "migrations": state}


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def metrics_text() -> str:
    """Prometheus text exposition (version 0.0.4)."""
    lines = [
        "# HELP cropstory_build_info Running version.",
        "# TYPE cropstory_build_info gauge",
        f'cropstory_build_info{{version="{_escape(app_version())}"}} 1',
        "# HELP cropstory_process_start_time_seconds Unix time the process started.",
        "# TYPE cropstory_process_start_time_seconds gauge",
        f"cropstory_process_start_time_seconds {STARTED_AT:.0f}",
        "# HELP cropstory_http_requests_total HTTP requests by method, route template and status class.",
        "# TYPE cropstory_http_requests_total counter",
    ]
    with _lock:
        http = sorted(_http_requests.items())
        seconds = sorted(_http_seconds.items())
        unhandled = sorted(_unhandled.items())
        upstream = sorted(_upstream.items())
        last = sorted(_upstream_last_error.items())
    lines += [f'cropstory_http_requests_total{{method="{m}",route="{_escape(r)}",status="{s}"}} {n}' for (m, r, s), n in http]
    lines += ["# HELP cropstory_http_request_seconds_total Time spent serving each route template.",
              "# TYPE cropstory_http_request_seconds_total counter"]
    lines += [f'cropstory_http_request_seconds_total{{route="{_escape(r)}"}} {v:.6f}' for r, v in seconds]
    lines += ["# HELP cropstory_unhandled_errors_total Unhandled exceptions by type (answered 500).",
              "# TYPE cropstory_unhandled_errors_total counter"]
    lines += [f'cropstory_unhandled_errors_total{{type="{_escape(k)}"}} {n}' for k, n in unhandled]
    lines += ["# HELP cropstory_upstream_calls_total Calls to external sources (NASA POWER, OpenAlex, Crossref) by outcome.",
              "# TYPE cropstory_upstream_calls_total counter"]
    lines += [f'cropstory_upstream_calls_total{{source="{s}",outcome="{_escape(o)}"}} {n}' for (s, o), n in upstream]
    lines += ["# HELP cropstory_upstream_last_error_timestamp_seconds Unix time of the latest failure per source.",
              "# TYPE cropstory_upstream_last_error_timestamp_seconds gauge"]
    lines += [f'cropstory_upstream_last_error_timestamp_seconds{{source="{s}",outcome="{_escape(o)}"}} {t:.0f}' for s, (t, o) in last]
    return "\n".join(lines) + "\n"


def metrics_allowed(request: Request) -> bool | None:
    """None: metrics disabled (no METRICS_TOKEN). True/False: bearer token matches or not."""
    import hmac

    token = os.getenv("METRICS_TOKEN", "")
    if len(token) < 16:
        return None
    given = request.headers.get("authorization", "")
    return hmac.compare_digest(given, f"Bearer {token}")


def reset_for_tests() -> None:
    with _lock:
        _http_requests.clear()
        _http_seconds.clear()
        _unhandled.clear()
        _upstream.clear()
        _upstream_last_error.clear()
