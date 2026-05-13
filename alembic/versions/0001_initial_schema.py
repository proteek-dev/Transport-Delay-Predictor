"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-13 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "agencies",
        sa.Column("agency_id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("url", sa.Text),
        sa.Column("timezone", sa.Text, nullable=False),
    )

    op.create_table(
        "routes",
        sa.Column("route_id", sa.Text, primary_key=True),
        sa.Column("agency_id", sa.Text, sa.ForeignKey("agencies.agency_id", ondelete="CASCADE")),
        sa.Column("short_name", sa.Text),
        sa.Column("long_name", sa.Text),
        sa.Column("route_type", sa.SmallInteger, nullable=False),
        sa.Column("color", sa.Text),
        sa.Column("text_color", sa.Text),
    )
    op.create_index("ix_routes_short_name", "routes", ["short_name"])

    op.create_table(
        "stops",
        sa.Column("stop_id", sa.Text, primary_key=True),
        sa.Column("code", sa.Text),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lon", sa.Float, nullable=False),
        sa.Column("location", Geography(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("location_type", sa.SmallInteger),
        sa.Column("parent_station", sa.Text),
        sa.Column("platform_code", sa.Text),
    )
    op.create_index("ix_stops_location", "stops", ["location"], postgresql_using="gist")
    op.create_index("ix_stops_name_trgm", "stops", ["name"], postgresql_using="gin",
                    postgresql_ops={"name": "gin_trgm_ops"})

    op.create_table(
        "trips",
        sa.Column("trip_id", sa.Text, primary_key=True),
        sa.Column("route_id", sa.Text, sa.ForeignKey("routes.route_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("service_id", sa.Text, nullable=False),
        sa.Column("headsign", sa.Text),
        sa.Column("short_name", sa.Text),
        sa.Column("direction_id", sa.SmallInteger),
        sa.Column("block_id", sa.Text),
        sa.Column("shape_id", sa.Text),
    )
    op.create_index("ix_trips_route_id", "trips", ["route_id"])
    op.create_index("ix_trips_service_id", "trips", ["service_id"])

    op.create_table(
        "stop_times",
        sa.Column("trip_id", sa.Text, sa.ForeignKey("trips.trip_id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("stop_sequence", sa.Integer, primary_key=True),
        sa.Column("stop_id", sa.Text, sa.ForeignKey("stops.stop_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("arrival_time", sa.Interval, nullable=False),
        sa.Column("departure_time", sa.Interval, nullable=False),
        sa.Column("pickup_type", sa.SmallInteger),
        sa.Column("drop_off_type", sa.SmallInteger),
        sa.Column("shape_dist_traveled", sa.Float),
    )
    op.create_index("ix_stop_times_stop_id", "stop_times", ["stop_id"])

    op.create_table(
        "calendar",
        sa.Column("service_id", sa.Text, primary_key=True),
        sa.Column("monday", sa.Boolean, nullable=False),
        sa.Column("tuesday", sa.Boolean, nullable=False),
        sa.Column("wednesday", sa.Boolean, nullable=False),
        sa.Column("thursday", sa.Boolean, nullable=False),
        sa.Column("friday", sa.Boolean, nullable=False),
        sa.Column("saturday", sa.Boolean, nullable=False),
        sa.Column("sunday", sa.Boolean, nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
    )

    op.create_table(
        "calendar_dates",
        sa.Column("service_id", sa.Text, primary_key=True),
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("exception_type", sa.SmallInteger, nullable=False),
    )

    op.create_table(
        "vehicle_positions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("vehicle_id", sa.Text, nullable=False),
        sa.Column("trip_id", sa.Text, index=True),
        sa.Column("route_id", sa.Text, index=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lon", sa.Float, nullable=False),
        sa.Column("location", Geography(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("bearing", sa.Float),
        sa.Column("speed", sa.Float),
        sa.Column("status", sa.SmallInteger),
        sa.Column("congestion_level", sa.SmallInteger),
        sa.Column("stop_sequence", sa.Integer),
        sa.Column("current_stop_id", sa.Text),
    )
    op.create_index("ix_vehicle_positions_recorded_at", "vehicle_positions", ["recorded_at"])
    op.create_index("ix_vehicle_positions_location", "vehicle_positions", ["location"],
                    postgresql_using="gist")
    op.create_index("ix_vehicle_positions_vehicle_time", "vehicle_positions",
                    ["vehicle_id", "recorded_at"])

    op.create_table(
        "trip_updates",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("trip_id", sa.Text, nullable=False, index=True),
        sa.Column("route_id", sa.Text, index=True),
        sa.Column("vehicle_id", sa.Text),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("start_date", sa.Date),
        sa.Column("schedule_relationship", sa.SmallInteger),
    )
    op.create_index("ix_trip_updates_recorded_at", "trip_updates", ["recorded_at"])

    op.create_table(
        "stop_time_updates",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("trip_update_id", sa.BigInteger,
                  sa.ForeignKey("trip_updates.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("stop_id", sa.Text, index=True),
        sa.Column("stop_sequence", sa.Integer),
        sa.Column("arrival_delay_seconds", sa.Integer),
        sa.Column("arrival_time", sa.DateTime(timezone=True)),
        sa.Column("departure_delay_seconds", sa.Integer),
        sa.Column("departure_time", sa.DateTime(timezone=True)),
        sa.Column("schedule_relationship", sa.SmallInteger),
    )

    op.create_table(
        "delay_observations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("route_id", sa.Text, nullable=False),
        sa.Column("trip_id", sa.Text, nullable=False),
        sa.Column("stop_id", sa.Text, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_date", sa.Date, nullable=False),
        sa.Column("hour_of_day", sa.SmallInteger, nullable=False),
        sa.Column("day_of_week", sa.SmallInteger, nullable=False),
        sa.Column("delay_seconds", sa.Integer, nullable=False),
    )
    op.create_index(
        "ix_delay_obs_route_stop_time", "delay_observations",
        ["route_id", "stop_id", "hour_of_day", "day_of_week"],
    )
    op.create_index("ix_delay_obs_observed_at", "delay_observations", ["observed_at"])
    op.create_unique_constraint(
        "uq_delay_obs_natural",
        "delay_observations",
        ["trip_id", "stop_id", "service_date"],
    )


def downgrade() -> None:
    op.drop_table("delay_observations")
    op.drop_table("stop_time_updates")
    op.drop_table("trip_updates")
    op.drop_table("vehicle_positions")
    op.drop_table("calendar_dates")
    op.drop_table("calendar")
    op.drop_table("stop_times")
    op.drop_table("trips")
    op.drop_table("stops")
    op.drop_table("routes")
    op.drop_table("agencies")
