# syntax=docker/dockerfile:1
# Drikr Systems training simulator API. Build context: repository root.
#   docker build -f apps/api/Dockerfile -t drikr-api:1.0.0 .

FROM python:3.12.14-slim-bookworm AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10
WORKDIR /src
COPY packages/ packages/
COPY apps/api/ apps/api/
RUN pip wheel --wheel-dir /wheels ./packages/contracts ./packages/simcore ./packages/scoring ./apps/api

FROM python:3.12.14-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DRIKR_MIGRATIONS_DIR=/app/database/migrations
# Apply Debian security updates released after the base image was built (keeps Trivy clean).
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 drikr && useradd --uid 10001 --gid drikr --no-create-home --shell /usr/sbin/nologin drikr
COPY --from=build /wheels /wheels
RUN pip install --no-index --find-links=/wheels drikr-api && rm -rf /wheels
WORKDIR /app
COPY database/migrations/ database/migrations/
USER drikr
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=2).status == 200 else 1)"
# Migrations are idempotent; running them at start keeps a fresh install to a single command.
CMD ["sh", "-c", "drikr-api migrate && exec uvicorn --factory drikr_api.main:app_factory --host 0.0.0.0 --port 8000 --no-server-header"]
