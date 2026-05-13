"""weather, public_holidays, route_delay_stats, training_features

Revision ID: 0002_features
Revises: 0001_initial
Create Date: 2026-05-13 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_features"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "weather_observations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("station_id", sa.Text, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("air_temp_c", sa.Float),
        sa.Column("rainfall_mm", sa.Float),
        sa.Column("humidity_pct", sa.Float),
        sa.Column("wind_speed_kmh", sa.Float),
        sa.Column("source", sa.Text),
        sa.UniqueConstraint("station_id", "observed_at", name="uq_weather_natural"),
    )
    op.create_index("ix_weather_obs_observed_at", "weather_observations", ["observed_at"])

    op.create_table(
        "public_holidays",
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("subdivision", sa.Text),
        sa.Column("source", sa.Text),
    )

    op.create_table(
        "route_delay_stats",
        sa.Column("route_id", sa.Text, primary_key=True),
        sa.Column("window_start", sa.Date, nullable=False),
        sa.Column("window_end", sa.Date, nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("avg_delay_seconds", sa.Float, nullable=False),
        sa.Column("p50_delay_seconds", sa.Float),
        sa.Column("p90_delay_seconds", sa.Float),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "training_features",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "observation_id",
            sa.BigInteger,
            sa.ForeignKey("delay_observations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("route_id", sa.Text, nullable=False),
        sa.Column("trip_id", sa.Text, nullable=False),
        sa.Column("stop_id", sa.Text, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_date", sa.Date, nullable=False),
        sa.Column("hour_of_day", sa.SmallInteger, nullable=False),
        sa.Column("day_of_week", sa.SmallInteger, nullable=False),
        sa.Column("is_weekend", sa.Boolean, nullable=False),
        sa.Column("is_public_holiday", sa.Boolean, nullable=False),
        sa.Column("month", sa.SmallInteger, nullable=False),
        sa.Column("air_temp_c", sa.Float),
        sa.Column("rainfall_mm", sa.Float),
        sa.Column("humidity_pct", sa.Float),
        sa.Column("route_avg_delay_30d_s", sa.Float),
        sa.Column("route_p50_delay_30d_s", sa.Float),
        sa.Column("route_p90_delay_30d_s", sa.Float),
        sa.Column("delay_seconds", sa.Integer, nullable=False),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_training_features_observed_at", "training_features", ["observed_at"])
    op.create_index("ix_training_features_route_id", "training_features", ["route_id"])
    op.create_index("ix_training_features_service_date", "training_features", ["service_date"])


def downgrade() -> None:
    op.drop_table("training_features")
    op.drop_table("route_delay_stats")
    op.drop_table("public_holidays")
    op.drop_table("weather_observations")
