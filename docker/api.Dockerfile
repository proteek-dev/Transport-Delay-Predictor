FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_HOME=/srv

WORKDIR ${APP_HOME}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libpq-dev \
        libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

# ---- Builder: install deps ----
FROM base AS builder

COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install --prefix=/install ".[dev]"

# ---- Runtime ----
FROM base AS runtime

COPY --from=builder /install /usr/local

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

RUN groupadd -r app && useradd -r -g app -d ${APP_HOME} app \
    && chown -R app:app ${APP_HOME}
USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
