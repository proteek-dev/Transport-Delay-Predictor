from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PublicHoliday(Base):
    """One row per public-holiday date applicable to Queensland."""

    __tablename__ = "public_holidays"

    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    subdivision: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
