"""Business dates. Timestamps are stored in UTC, but "today" for trips is the company's local
date (BUSINESS_TIMEZONE, Europe/Kyiv): a trip that ends on the 17th is completed on the 18th in
Kyiv, not at 22:00 / 21:00 UTC. zoneinfo needs the `tzdata` package on Windows.

Never use date.today() in app/ (the server's own zone may differ): tests/test_business_dates.py
fails if it appears. Tests move time by patching clock.now.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import settings


def _zone() -> ZoneInfo:
    return ZoneInfo(settings.business_timezone)


def now() -> datetime:
    """The current moment (UTC). The one place tests patch to move "today"."""
    return datetime.now(timezone.utc)


def today(at: datetime | None = None) -> date:
    """The business date (Kyiv) of `at`, or of now."""
    return (at or now()).astimezone(_zone()).date()


def tomorrow() -> date:
    """The first date a trip can start (scenario 4.5.3: booking is for tomorrow at the earliest)."""
    return today() + timedelta(days=1)


def day_start(day: date) -> datetime:
    """Midnight of a business date as an aware datetime, for filtering UTC timestamps by Kyiv
    days: [day_start(d), day_start(d + 1 day)) is the whole of `d` in Kyiv."""
    return datetime.combine(day, time.min, _zone())
