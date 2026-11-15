# CropStory API image (ABB-30). Multi-arch (amd64 for CI/servers, arm64 for the Raspberry Pi).
# Python and dependencies are managed by uv only, from the committed uv.lock.
FROM ghcr.io/astral-sh/uv:0.12.21 AS uv

FROM python:3.12-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY alembic.ini ./
COPY migrations ./migrations
COPY agroblackbox ./agroblackbox
# Editable install: the package stays at /app/agroblackbox next to alembic.ini/migrations, which
# /api/ready uses to know this build's migration head.
RUN uv sync --locked --no-dev

FROM python:3.12-slim-bookworm
ARG APP_VERSION=dev
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_FORMAT=json \
    APP_VERSION=$APP_VERSION
RUN useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app /app
WORKDIR /app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=4s --start-period=20s --retries=4 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]
# No access log: uvicorn would print raw URLs (coordinates travel in query strings). The app logs
# route templates with a request id instead (agroblackbox/observability.py).
CMD ["uvicorn", "agroblackbox.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]
