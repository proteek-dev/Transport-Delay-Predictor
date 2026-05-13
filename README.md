# Transport Delay Predictor

Production-grade public transport delay prediction API.

- **Stack**: Python 3.11, FastAPI, SQLAlchemy 2 (async + asyncpg), PostgreSQL 16 + PostGIS, Redis 7, Celery, Docker Compose.
- **Data**: [TransLink Queensland](https://gtfsrt.api.translink.com.au/) GTFS static + GTFS-Realtime (TripUpdates and VehiclePositions). Public, no auth required.
- **What it does**: ingests static + realtime feeds on a schedule, exposes a REST API for stops/trips/vehicles, and serves delay predictions backed by a buckets-of-history estimator with realtime override.

## Architecture

```
                          ┌─────────────┐
   GTFS-RT feeds  ───▶    │   Celery    │ ──▶ Postgres + PostGIS
   (TransLink)            │  worker +   │
                          │    beat     │
                          └─────────────┘
                                 │
                                 ▼
                          ┌─────────────┐    ┌───────┐
   HTTP clients   ───▶    │   FastAPI   │ ◀──│ Redis │ (cache + broker)
                          └─────────────┘    └───────┘
```

- **API** (`app/main.py`) serves `/api/v1/{stops,trips,vehicles,predictions}` and `/health`.
- **Worker** (`app/workers/`) runs four scheduled tasks: poll trip updates, poll vehicle positions, prune old realtime rows, refresh static GTFS daily.
- **Predictor** (`app/services/predictor.py`) computes the expected delay for a `(route_id, stop_id, hour, day_of_week)` bucket from `delay_observations`, with a route-wide fallback and Redis-cached results.

## Folder layout

```
.
├── app/
│   ├── api/
│   │   ├── deps.py                # FastAPI dependencies (DB session)
│   │   └── routes/                # health, stops, trips, vehicles, predictions
│   ├── core/                      # database, redis, logging
│   ├── models/                    # SQLAlchemy 2 ORM (static + realtime + observations)
│   ├── schemas/                   # Pydantic v2 request/response models
│   ├── services/
│   │   ├── gtfs_static.py         # zip download + upsert
│   │   ├── gtfs_realtime.py       # protobuf parse + insert + observation extraction
│   │   ├── predictor.py           # delay prediction
│   │   └── cache.py               # redis helpers
│   ├── workers/
│   │   ├── celery_app.py          # broker config + beat schedule
│   │   └── tasks.py               # @shared_task wrappers
│   ├── config.py                  # pydantic-settings
│   └── main.py                    # FastAPI app factory
├── alembic/                       # migrations (0001 = initial schema)
├── docker/
│   ├── api.Dockerfile
│   ├── worker.Dockerfile
│   └── postgres-init.sql          # enables postgis, pg_trgm, btree_gist
├── tests/                         # pytest scaffold
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── alembic.ini
└── .env.example
```

## Quick start

```bash
make build         # build the api + worker images
make up            # postgres, redis, api, worker, beat
make migrate       # apply alembic migrations (creates schema + extensions)
make ingest-static # pull the SEQ GTFS zip and load agencies/routes/stops/trips/stop_times
```

The beat container will start polling realtime feeds immediately on the cadence in `.env` (default 60s).

Open the API:

- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | DB + Redis liveness probes |
| `GET` | `/api/v1/stops` | List stops with optional fuzzy search (`?q=`) |
| `GET` | `/api/v1/stops/nearby?lat=&lon=&radius_m=` | PostGIS `ST_DWithin` search |
| `GET` | `/api/v1/stops/{stop_id}` | Single stop |
| `GET` | `/api/v1/stops/{stop_id}/departures` | Upcoming scheduled departures enriched with realtime delay or model prediction |
| `GET` | `/api/v1/trips/{trip_id}` | Trip + ordered stop_times |
| `GET` | `/api/v1/vehicles?route_id=&bbox=` | Latest known position per vehicle |
| `GET` | `/api/v1/predictions?route_id=&stop_id=&target_time=` | Predicted delay (seconds) for a route/stop at a given time |
| `POST` | `/api/v1/predictions` | Same prediction, JSON body |

## Feature pipeline (for model training)

Beyond the realtime predictor, a separate pipeline materializes a `training_features` table joining GTFS delay observations with calendar, weather, and route-history features. See [app/services/feature_pipeline.py](app/services/feature_pipeline.py).

**Sources:**

| Feature group | Table populated by | Schedule |
| --- | --- | --- |
| Delays + calendar (hour, day-of-week, month) | `delay_observations` (from GTFS-RT poller) | 60s |
| Weather (air temp, rainfall, humidity) | `weather_observations` ← BOM `IDQ60901` JSON | 30 min |
| Public holiday flag (QLD) | `public_holidays` ← Nager.Date `/api/v3/PublicHolidays/{year}/AU` | weekly |
| Route-level history (avg, p50, p90) | `route_delay_stats` ← rolling 30d aggregate | every 6h |
| Joined output | `training_features` ← INSERT…SELECT…ON CONFLICT | every 6h |

**Output columns** (`training_features`): `observation_id`, `route_id`, `trip_id`, `stop_id`, `observed_at`, `service_date`, `hour_of_day`, `day_of_week`, `is_weekend`, `is_public_holiday`, `month`, `air_temp_c`, `rainfall_mm`, `humidity_pct`, `route_avg_delay_30d_s`, `route_p50_delay_30d_s`, `route_p90_delay_30d_s`, `delay_seconds` (target), `materialized_at`.

**Bootstrap & inspection:**

```bash
make sync-holidays      # seed public_holidays for current + next year
make ingest-weather     # pull recent BOM observations
make rebuild-features   # refresh route stats and materialize training_features
make bootstrap-features # all three in order
```

API endpoints:
- `GET /api/v1/features?route_id=…&since=…&limit=…` — browse feature rows
- `POST /api/v1/features/refresh?window_days=…` — trigger the pipeline manually

**Design notes:**

- Weather rows are joined via a `LATERAL` averaging across the configured BOM stations in a ±90/30-minute window around each observation — robust to occasional missing readings at any one station.
- The job is fully idempotent: `ON CONFLICT (observation_id) DO UPDATE` keeps derived columns fresh as weather/holiday/route-stats inputs evolve.
- All windows are configurable: `FEATURE_WINDOW_DAYS`, `BOM_POLL_INTERVAL_SECONDS`, `FEATURE_REBUILD_INTERVAL_SECONDS`.

## How predictions work

Each `TripUpdate.StopTimeUpdate` with a `delay` field gets flattened into a `delay_observations` row keyed by `(trip_id, stop_id, service_date)`. Predictions aggregate that table over a rolling window (default 14 days):

1. **Bucket mean**: average delay for `(route_id, stop_id, hour_of_day, day_of_week)` if ≥ `PREDICTOR_MIN_OBSERVATIONS` samples exist. Returns p50/p90 via `percentile_cont`.
2. **Route fallback**: route-wide mean if the bucket is sparse — half-weighted confidence.
3. **No data**: returns `0` with `confidence = 0`.

Results are cached in Redis for 60s (configurable via `PREDICTOR_CACHE_TTL_SECONDS`). This is intentionally a transparent baseline — swap `app/services/predictor.py` for a gradient-boosted or RNN model once you have enough observations to train one.

## Make targets

Run `make help` for the full list.

```
build / pull / up / down / nuke / restart / ps / logs / logs-api / logs-worker
migrate / migration m="msg" / downgrade / psql
ingest-static / ingest-rt
shell / lint / fmt / test / test-cov
```

## Configuration

All knobs live in `.env` (see `.env.example`). Highlights:

- `GTFS_RT_POLL_INTERVAL` — seconds between realtime polls (default 60).
- `GTFS_STATIC_REFRESH_HOURS` — how often beat re-pulls the static zip.
- `PREDICTOR_HISTORY_DAYS` — rolling window for the bucketed estimator.
- `PREDICTOR_MIN_OBSERVATIONS` — threshold before falling back to route mean.

## Notes & gotchas

- **GTFS times can exceed 24h** (e.g. `25:30:00` for trips that cross midnight) — they're stored as `INTERVAL` in `stop_times`.
- **Vehicle positions write-heavy**: `vehicle_positions` is append-only; the `prune_realtime` beat task drops rows older than 6h. Long-term retention lives in `delay_observations`.
- **Static feed wipes `stop_times`** wholesale because trips can be renumbered between releases; agencies/routes/stops/trips are upserted via Postgres `ON CONFLICT`.
- **Timezones**: TransLink agency timezone is `Australia/Brisbane` (UTC+10, no DST). All `DateTime` columns are stored in UTC; the predictor uses `hour`/`weekday` from the `target_time` you pass, so feed it agency-local time if you want bucket alignment.
- **No auth on TransLink endpoints**, but be polite — the default 60s cadence is well under their published rate limits.

## Tests

```
make test          # full suite
make test-cov      # with coverage
```

Tests cover the GTFS parser (no DB) and the predictor confidence curve, plus an OpenAPI shape check against the live FastAPI app. Integration tests against PostGIS are scaffolded but left to the next iteration — point a test database at `APP_ENV=test` to add them.
