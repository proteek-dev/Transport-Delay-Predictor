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
        libpq-dev \
        libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder

COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install --prefix=/install "."

FROM base AS runtime

COPY --from=builder /install /usr/local

COPY app ./app

RUN groupadd -r app && useradd -r -g app -d ${APP_HOME} app \
    && chown -R app:app ${APP_HOME}
USER app

CMD ["celery", "-A", "app.workers.celery_app", "worker", "--loglevel=INFO"]
