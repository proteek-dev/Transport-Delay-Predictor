.DEFAULT_GOAL := help
SHELL := /bin/bash

COMPOSE := docker compose
SERVICE_API := api
SERVICE_WORKER := worker
SERVICE_BEAT := beat
SERVICE_DB := postgres

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- Setup ----

.PHONY: env
env: ## Copy .env.example to .env if missing
	@test -f .env || cp .env.example .env && echo ".env ready"

.PHONY: build
build: env ## Build all docker images
	$(COMPOSE) build

.PHONY: pull
pull: ## Pull base images
	$(COMPOSE) pull

# ---- Lifecycle ----

.PHONY: up
up: env ## Start the full stack in the background
	$(COMPOSE) up -d

.PHONY: down
down: ## Stop the stack (keeps volumes)
	$(COMPOSE) down

.PHONY: nuke
nuke: ## Stop the stack and drop volumes (destroys DB data)
	$(COMPOSE) down -v

.PHONY: restart
restart: down up ## Restart the stack

.PHONY: ps
ps: ## Show running services
	$(COMPOSE) ps

.PHONY: logs
logs: ## Tail logs from all services
	$(COMPOSE) logs -f --tail=200

.PHONY: logs-api
logs-api: ## Tail logs from the API service
	$(COMPOSE) logs -f --tail=200 $(SERVICE_API)

.PHONY: logs-worker
logs-worker: ## Tail logs from the Celery worker
	$(COMPOSE) logs -f --tail=200 $(SERVICE_WORKER)

# ---- DB / migrations ----

.PHONY: migrate
migrate: ## Apply Alembic migrations
	$(COMPOSE) run --rm $(SERVICE_API) alembic upgrade head

.PHONY: migration
migration: ## Generate a new Alembic migration (usage: make migration m="add foo")
	$(COMPOSE) run --rm $(SERVICE_API) alembic revision --autogenerate -m "$(m)"

.PHONY: downgrade
downgrade: ## Roll back one migration
	$(COMPOSE) run --rm $(SERVICE_API) alembic downgrade -1

.PHONY: psql
psql: ## Open a psql shell against the running db (reads creds from .env)
	$(COMPOSE) --env-file .env exec $(SERVICE_DB) sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

# ---- GTFS ingestion ----

.PHONY: ingest-static
ingest-static: ## Download + load the static GTFS feed
	$(COMPOSE) run --rm $(SERVICE_API) python -m app.services.gtfs_static

.PHONY: ingest-rt
ingest-rt: ## Trigger a one-shot GTFS-RT poll (trip updates + positions)
	$(COMPOSE) exec $(SERVICE_WORKER) celery -A app.workers.celery_app call app.workers.tasks.poll_trip_updates
	$(COMPOSE) exec $(SERVICE_WORKER) celery -A app.workers.celery_app call app.workers.tasks.poll_vehicle_positions

# ---- Feature pipeline ----

.PHONY: sync-holidays
sync-holidays: ## Sync QLD public holidays (current + next year) from Nager.Date
	$(COMPOSE) exec $(SERVICE_WORKER) celery -A app.workers.celery_app call app.workers.tasks.sync_holidays

.PHONY: ingest-weather
ingest-weather: ## Fetch BOM weather observations for the configured SEQ stations
	$(COMPOSE) exec $(SERVICE_WORKER) celery -A app.workers.celery_app call app.workers.tasks.poll_weather

.PHONY: rebuild-features
rebuild-features: ## Refresh route delay stats and rebuild training_features
	$(COMPOSE) exec $(SERVICE_WORKER) celery -A app.workers.celery_app call app.workers.tasks.refresh_route_stats
	$(COMPOSE) exec $(SERVICE_WORKER) celery -A app.workers.celery_app call app.workers.tasks.rebuild_features

.PHONY: bootstrap-features
bootstrap-features: sync-holidays ingest-weather rebuild-features ## One-shot pipeline run from scratch

# ---- Dev ----

.PHONY: shell
shell: ## Open a shell in the API container
	$(COMPOSE) exec $(SERVICE_API) /bin/bash

.PHONY: lint
lint: ## Run ruff + mypy
	$(COMPOSE) run --rm $(SERVICE_API) ruff check app tests
	$(COMPOSE) run --rm $(SERVICE_API) mypy app

.PHONY: fmt
fmt: ## Auto-fix lint issues
	$(COMPOSE) run --rm $(SERVICE_API) ruff check --fix app tests
	$(COMPOSE) run --rm $(SERVICE_API) ruff format app tests

.PHONY: test
test: ## Run pytest
	$(COMPOSE) run --rm -e APP_ENV=test $(SERVICE_API) pytest

.PHONY: test-cov
test-cov: ## Run pytest with coverage
	$(COMPOSE) run --rm -e APP_ENV=test $(SERVICE_API) pytest --cov=app --cov-report=term-missing
