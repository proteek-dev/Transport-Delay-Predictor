# Transport Delay Predictor

Production-grade public transport delay prediction API.

- **Stack**: Python 3.11, FastAPI, SQLAlchemy 2 (async + asyncpg), PostgreSQL 16 + PostGIS, Redis 7, Celery, Docker Compose. ML: scikit-learn + XGBoost, persisted via joblib.
- **Data sources**:
  - [TransLink Queensland](https://gtfsrt.api.translink.com.au/) GTFS static + GTFS-Realtime (TripUpdates, VehiclePositions). Public, no auth.
  - [Bureau of Meteorology](http://www.bom.gov.au/) `IDQ60901` JSON observations for SEQ stations.
  - [Nager.Date](https://date.nager.at) for Australian public holidays (national + QLD).
- **What it does**: ingests static + realtime feeds on a schedule, serves delay predictions via a buckets-of-history estimator with realtime override, materializes a feature table joining delays with calendar / weather / route-history context, and trains a daily-refreshed XGBoost regressor on top for richer point estimates.

## Architecture

```
   TransLink GTFS-RT  ──┐
   BOM SEQ weather    ──┼──▶  Celery worker + beat  ──▶  Postgres + PostGIS
   Nager.Date QLD     ──┘                                     ▲
                                                              │
                          ┌─────────────┐    ┌───────┐        │
   HTTP clients   ───▶    │   FastAPI   │ ◀──│ Redis │ ◀──────┘
                          └─────────────┘    └───────┘
                                         (cache + Celery broker)
```

- **API** (`app/main.py`) serves `/api/v1/{stops,trips,vehicles,predictions,features}` and `/health`.
- **Worker** (`app/workers/`) runs nine scheduled tasks: poll trip updates (60s), poll vehicle positions (60s), prune realtime rows (15m), refresh static GTFS (daily), poll BOM weather (30m), sync public holidays (weekly), refresh route delay stats (6h), rebuild training features (6h), retrain XGBoost delay model (daily 02:30 UTC).
- **Predictor** (`app/services/predictor.py`) computes the expected delay for a `(route_id, stop_id, hour, day_of_week)` bucket from `delay_observations`, with a route-wide fallback and Redis-cached results.
- **Feature pipeline** (`app/services/feature_pipeline.py`) joins `delay_observations` with `weather_observations`, `public_holidays`, and `route_delay_stats` into a `training_features` table (one row per observation, `delay_seconds` is the label).
- **ML model** (`app/services/ml_predictor.py`) trains a scikit-learn pipeline (OrdinalEncoder + XGBRegressor) on `training_features`, evaluates RMSE on a held-out split, and serializes the fitted pipeline to disk via joblib. Celery beat retrains every 24 hours.

## Folder layout

```
.
├── app/
│   ├── api/
│   │   ├── deps.py                # FastAPI dependencies (DB session)
│   │   └── routes/                # health, stops, trips, vehicles, predictions, features
│   ├── core/                      # database, redis, logging
│   ├── models/                    # SQLAlchemy 2 ORM
│   │   ├── gtfs_static.py         #   agencies, routes, stops, trips, stop_times, calendar(_dates)
│   │   ├── realtime.py            #   vehicle_positions, trip_updates, stop_time_updates
│   │   ├── observations.py        #   delay_observations (deduped trip×stop×day delays)
│   │   ├── weather.py             #   weather_observations
│   │   ├── holidays.py            #   public_holidays
│   │   └── features.py            #   route_delay_stats, training_features
│   ├── schemas/                   # Pydantic v2 request/response models
│   ├── services/
│   │   ├── gtfs_static.py         # zip download + upsert
│   │   ├── gtfs_realtime.py       # protobuf parse + insert + observation extraction
│   │   ├── bom_weather.py         # BOM IDQ60901 JSON fetch + parse
│   │   ├── holidays.py            # Nager.Date /AU sync (national + AU-QLD)
│   │   ├── feature_pipeline.py    # route stats refresh + training_features build
│   │   ├── ml_predictor.py        # sklearn + XGBoost trainer, joblib persistence
│   │   ├── predictor.py           # delay prediction
│   │   └── cache.py               # redis helpers
│   ├── workers/
│   │   ├── celery_app.py          # broker config + beat schedule
│   │   └── tasks.py               # @shared_task wrappers
│   ├── config.py                  # pydantic-settings
│   └── main.py                    # FastAPI app factory
├── alembic/                       # migrations
│   └── versions/
│       ├── 0001_initial_schema.py
│       └── 0002_weather_holidays_features.py
├── docker/
│   ├── api.Dockerfile
│   ├── worker.Dockerfile
│   └── postgres-init.sql          # enables postgis, pg_trgm, btree_gist
├── infra/
│   ├── terraform/                 # AWS free-tier stack (EC2 + RDS + S3 + ECR + IAM OIDC)
│   └── scripts/deploy.sh          # invoked on the EC2 via SSM by the deploy workflow
├── .github/workflows/
│   ├── ci.yml                     # ruff + mypy + pytest on PR / push
│   └── deploy.yml                 # build + push to ECR, SSM-deploy on push to main
├── tests/                         # pytest scaffold (parsers + OpenAPI shape)
├── docker-compose.yml             # local dev (builds locally, postgres in-cluster)
├── docker-compose.aws.yml         # prod (pulls ECR images, external RDS)
├── Makefile
├── pyproject.toml
├── alembic.ini
└── .env.example
```

## Quick start (local dev)

```bash
make build         # build the api + worker images
make up            # postgres, redis, api, worker, beat
make migrate       # apply alembic migrations (creates schema + extensions)
make ingest-static # pull the SEQ GTFS zip and load agencies/routes/stops/trips/stop_times
```

The beat container will start polling realtime feeds immediately on the cadence in `.env` (default 60s).

## AWS Setup (Console)

The deploy pipeline (`.github/workflows/deploy.yml`) targets a hand-provisioned AWS stack — there is no IaC committed to this repo. Create the six resources below in the AWS Console (once), populate the five GitHub repository entries, then every push to `main` builds, pushes to ECR, and SSM-deploys onto the EC2 host.

### AWS resources to create

| # | Resource | Notes |
| --- | --- | --- |
| 1 | **EC2 instance** (`t2.micro`, Amazon Linux 2023) | Place in the default VPC's public subnet. Attach an EC2 security group allowing inbound TCP 80 and 8000 from `0.0.0.0/0`. Attach the IAM instance profile from row 5. Install Docker + the Compose v2 plugin, clone the repo to `/opt/transport-delay-predictor`, and write `/opt/transport-delay-predictor/.env` (DB URLs, `MODEL_S3_BUCKET`, `ECR_REGISTRY`, etc.). |
| 2 | **RDS PostgreSQL** (`db.t3.micro`, Postgres 16) | Single-AZ, 20 GB gp2, encrypted, **not** publicly accessible. Attach a security group allowing TCP 5432 **only** from the EC2 security group. After provisioning, connect with `psql` and run `CREATE EXTENSION postgis; CREATE EXTENSION pg_trgm; CREATE EXTENSION btree_gist;`. |
| 3 | **S3 bucket** for model artefacts | Block all public access, enable SSE-S3 (AES256), enable versioning, add a lifecycle rule expiring non-current versions after 30 days. The value of this bucket's name goes into the EC2's `.env` as `MODEL_S3_BUCKET`. |
| 4 | **ECR repositories** ×2 | Names: `transport-delay-predictor/api` and `transport-delay-predictor/worker`. Add an identical lifecycle policy on each that expires all but the 5 most recent images (otherwise you'll blow through the 500 MB free-tier storage). |
| 5 | **IAM role for the EC2 instance** | Trust policy: `ec2.amazonaws.com`. Permissions: AWS-managed `AmazonSSMManagedInstanceCore`, plus an inline policy granting `ecr:GetAuthorizationToken` + `ecr:BatchGetImage` + `ecr:GetDownloadUrlForLayer` (`*`), and `s3:GetObject`/`s3:PutObject`/`s3:ListBucket` scoped to the bucket from row 3. Create an instance profile that wraps this role and attach it to the EC2 in row 1. |
| 6 | **IAM OIDC identity provider + role** for GitHub Actions | Provider URL: `https://token.actions.githubusercontent.com`, audience `sts.amazonaws.com`. Create a role with a trust policy that conditions on `repo:<owner>/<repo>:ref:refs/heads/main`. Permissions: `ecr:GetAuthorizationToken` + the full ECR push set (`BatchCheckLayerAvailability`, `CompleteLayerUpload`, `InitiateLayerUpload`, `PutImage`, `UploadLayerPart`, `BatchGetImage`) on `*`, plus `ssm:SendCommand` / `ssm:GetCommandInvocation` on `*`. |

### GitHub repository entries

In the GitHub repo, open **Settings → Secrets and variables → Actions** and add these five entries. The first two live on the **Secrets** tab; the rest on the **Variables** tab.

| # | Name | Tab | Required? | Where to get the value |
| --- | --- | --- | --- | --- |
| 1 | `AWS_DEPLOY_ROLE_ARN` | Secrets | **Required** | ARN of the IAM role from resource 6. The workflow assumes it via OIDC — no static AWS keys ever leave AWS. |
| 2 | `AWS_EC2_INSTANCE_ID` | Secrets | **Required** | `i-…` instance ID of the EC2 from resource 1. Used as the `--instance-ids` target for `aws ssm send-command`. |
| 3 | `AWS_REGION` | Variables | Recommended | The region your stack lives in (e.g. `us-east-1`). `deploy.yml` falls back to `us-east-1` if unset, but set it explicitly to avoid surprises. |
| 4 | `AWS_ACCOUNT_ID` | Variables | Recommended | Your 12-digit AWS account ID. The workflow currently derives it via `sts get-caller-identity`; storing it makes diagnostics and manual ECR pulls easier. |
| 5 | `EC2_PUBLIC_HOSTNAME` | Variables | Recommended | Public DNS or IP of the EC2 instance. Used for post-deploy smoke checks (`curl http://$EC2_PUBLIC_HOSTNAME/health`). Not consumed by `deploy.yml` directly. |

Once both lists are populated, the next push to `main` will:

1. Assume the OIDC role and log into ECR.
2. Build `api` and `worker` images and push them tagged with the short Git SHA + `latest`.
3. Invoke `infra/scripts/deploy.sh` on the EC2 host via SSM — pulls the new images, runs `alembic upgrade head`, brings up `docker-compose.aws.yml`, no SSH required.

## CI

`.github/workflows/ci.yml` runs `ruff`, `mypy`, and `pytest` on every PR and push. The mypy step is non-gating until the strict-mode debt is paid down.

Open the API:

- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | DB + Redis liveness probes |
| `GET` | `/predict?route_id=&stop_id=&datetime=` | Point estimate + empirical confidence interval. Uses the trained XGBoost model when present, else the bucket mean. |
| `GET` | `/delays/live?route_id=&stop_id=&limit=` | Current delays from the latest GTFS-RT snapshot |
| `GET` | `/api/v1/stops` | List stops with optional fuzzy search (`?q=`) |
| `GET` | `/api/v1/stops/nearby?lat=&lon=&radius_m=` | PostGIS `ST_DWithin` search |
| `GET` | `/api/v1/stops/{stop_id}` | Single stop |
| `GET` | `/api/v1/stops/{stop_id}/departures` | Upcoming scheduled departures enriched with realtime delay or model prediction |
| `GET` | `/api/v1/trips/{trip_id}` | Trip + ordered stop_times |
| `GET` | `/api/v1/vehicles?route_id=&bbox=` | Latest known position per vehicle |
| `GET` | `/api/v1/predictions?route_id=&stop_id=&target_time=` | Bucketed predictor (legacy shape; no confidence interval). |
| `POST` | `/api/v1/predictions` | Same prediction, JSON body |
| `GET` | `/api/v1/features?route_id=&since=&limit=` | Browse `training_features` rows |
| `POST` | `/api/v1/features/refresh?window_days=` | Trigger the feature pipeline on demand |

### `GET /predict`

Returns a point estimate of `delay_seconds` plus an empirical confidence interval:

```json
{
  "route_id": "100-1234",
  "stop_id": "10001",
  "datetime": "2026-05-13T08:15:00+10:00",
  "predicted_delay_seconds": 64,
  "confidence_interval": {
    "lower_seconds": 12,
    "upper_seconds": 142,
    "level": 0.8
  },
  "method": "ml_model",
  "sample_size": 187,
  "confidence": 0.82
}
```

- `method` is one of `ml_model` (joblib loaded + bucket has enough samples), `bucket_mean`, `route_fallback`, or `no_data`.
- `confidence_interval` is the empirical [p10, p90] from `delay_observations` for the same `(route_id, stop_id, hour_of_day, day_of_week)` bucket. `null` when the bucket has fewer than `PREDICTOR_MIN_OBSERVATIONS` rows.
- The trained model artifact is reloaded transparently on file mtime change (no restart needed after `make train-model` finishes).

### `GET /delays/live`

Returns the most recent `StopTimeUpdate` rows from `trip_updates` within `snapshot_window_seconds` (default 90s) of the latest poll. `snapshot_at` is the anchor — `null` when no realtime data has landed yet.

```json
{
  "snapshot_at": "2026-05-13T08:14:32Z",
  "count": 2,
  "delays": [
    {
      "trip_id": "12345",
      "route_id": "100-1234",
      "stop_id": "10001",
      "stop_sequence": 4,
      "arrival_delay_seconds": 45,
      "departure_delay_seconds": 60,
      "delay_seconds": 60,
      "arrival_time": "2026-05-13T08:15:30Z",
      "departure_time": "2026-05-13T08:16:00Z",
      "recorded_at": "2026-05-13T08:14:32Z"
    }
  ]
}
```

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

Results are cached in Redis for 60s (configurable via `PREDICTOR_CACHE_TTL_SECONDS`). This is intentionally a transparent baseline — the gradient-boosted alternative below trains directly on the same feature table.

## ML model (XGBoost)

A scikit-learn pipeline in [app/services/ml_predictor.py](app/services/ml_predictor.py) trains an XGBoost regressor on the `training_features` table and serializes it to `/srv/models/delay_predictor.joblib` (a named Docker volume so the artifact survives container restarts).

**Features**: `(route_id, stop_id, hour_of_day, day_of_week, weather_condition)`, where `weather_condition` is bucketed from `rainfall_mm` (`clear` / `light_rain` >0.2 mm / `heavy_rain` >2 mm / `unknown` for NULL).

**Pipeline shape**:

```
ColumnTransformer
  ├── OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
  │       on [route_id, stop_id, weather_condition]
  └── passthrough on [hour_of_day, day_of_week]
        ↓
XGBRegressor(objective='reg:squarederror', tree_method='hist',
             n_estimators=400, max_depth=6, learning_rate=0.05)
```

**Training run** (`make train-model`, or daily at `MODEL_RETRAIN_HOUR_UTC:MODEL_RETRAIN_MINUTE_UTC`):

1. Pull the trailing `MODEL_TRAINING_WINDOW_DAYS` of rows from `training_features`.
2. `train_test_split(test_size=MODEL_TEST_SIZE, random_state=42)`.
3. Fit pipeline, compute RMSE on both splits, log metrics via structlog.
4. `joblib.dump({pipeline, metrics}, MODEL_ARTIFACT_PATH)`.

If the available sample count is below `MODEL_MIN_TRAINING_SAMPLES` (default 200), the task logs a warning and skips — no half-trained artifact is written.

**Inference**: `predict_single(pipeline, route_id=…, stop_id=…, hour=…, day_of_week=…, weather_condition=…)` returns a float. Unseen `route_id`/`stop_id`/`weather_condition` values degrade gracefully via the `-1` sentinel rather than raising at predict time.

**Bootstrap**:

```bash
make bootstrap-features   # ensure training_features has rows
make train-model          # fit + serialize the joblib
```

## Make targets

Run `make help` for the full list.

```
build / pull / up / down / nuke / restart / ps / logs / logs-api / logs-worker
migrate / migration m="msg" / downgrade / psql
ingest-static / ingest-rt
sync-holidays / ingest-weather / rebuild-features / bootstrap-features
train-model
shell / lint / fmt / test / test-cov
```

## Configuration

All knobs live in `.env` (see `.env.example`). Highlights:

- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` — required; no defaults in `docker-compose.yml` or app config so no credentials ever land in version control.
- `GTFS_RT_POLL_INTERVAL` — seconds between realtime polls (default 60).
- `GTFS_STATIC_REFRESH_HOURS` — how often beat re-pulls the static zip.
- `PREDICTOR_HISTORY_DAYS` — rolling window for the bucketed estimator.
- `PREDICTOR_MIN_OBSERVATIONS` — threshold before falling back to route mean.
- `BOM_STATION_IDS` — list of BOM station IDs to poll (default Brisbane + Brisbane Airport).
- `BOM_USER_AGENT` — required; BOM rejects requests with default httpx user agents.
- `BOM_POLL_INTERVAL_SECONDS` — weather poll cadence (default 30 min).
- `FEATURE_WINDOW_DAYS` — trailing window for `route_delay_stats` and `training_features`.
- `FEATURE_REBUILD_INTERVAL_SECONDS` — how often beat refreshes route stats + training features.
- `MODEL_ARTIFACT_PATH` — where the trained joblib lands (default `/srv/models/delay_predictor.joblib`, backed by the `model_data` Docker volume).
- `MODEL_TRAINING_WINDOW_DAYS` — trailing window of `training_features` used for fitting.
- `MODEL_MIN_TRAINING_SAMPLES` — skip retraining if fewer rows are available (default 200).
- `MODEL_TEST_SIZE` — `train_test_split` test fraction (default 0.2).
- `MODEL_N_ESTIMATORS` / `MODEL_MAX_DEPTH` / `MODEL_LEARNING_RATE` — XGBoost hyperparameters.
- `MODEL_RETRAIN_HOUR_UTC` / `MODEL_RETRAIN_MINUTE_UTC` — daily retrain time (default 02:30 UTC = 12:30 AEST).
- `MODEL_S3_BUCKET` / `MODEL_S3_KEY` — when `MODEL_S3_BUCKET` is set, `save_model` uploads the joblib to S3 after the local write and `get_model` pulls from S3 with ETag-based caching. Leave `MODEL_S3_BUCKET` empty (the default) for local dev — the Docker named volume stays the only backend.

## Notes & gotchas

- **GTFS times can exceed 24h** (e.g. `25:30:00` for trips that cross midnight) — they're stored as `INTERVAL` in `stop_times`.
- **Vehicle positions write-heavy**: `vehicle_positions` is append-only; the `prune_realtime` beat task drops rows older than 6h. Long-term retention lives in `delay_observations`.
- **Static feed wipes `stop_times`** wholesale because trips can be renumbered between releases; agencies/routes/stops/trips are upserted via Postgres `ON CONFLICT`.
- **Timezones**: TransLink agency timezone is `Australia/Brisbane` (UTC+10, no DST). All `DateTime` columns are stored in UTC; the predictor uses `hour`/`weekday` from the `target_time` you pass, so feed it agency-local time if you want bucket alignment.
- **No auth on TransLink endpoints**, but be polite — the default 60s cadence is well under their published rate limits.
- **BOM blocks default user agents**: the BOM JSON endpoint returns HTTP 403 to bare httpx/python requests, so `BOM_USER_AGENT` is required.
- **Secrets**: no credentials are committed. `docker-compose.yml` uses the `${VAR:?error}` form for Postgres user/password/db, and `app/config.py` defaults for DB URLs are empty strings — `.env` is the single source of truth (`make env` seeds it from `.env.example`).

## Tests

```
make test          # full suite
make test-cov      # with coverage
```

Tests cover the GTFS static parser, the BOM weather parser, the Nager.Date holidays parser, the predictor confidence curve, the ML pipeline (weather bucketing, train/test/joblib roundtrip, unseen-category robustness), and an OpenAPI shape check against the live FastAPI app. Integration tests against PostGIS are scaffolded but left to the next iteration — point a test database at `APP_ENV=test` to add them.

------
