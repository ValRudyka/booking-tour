"""Business dates. Timestamps are stored in UTC, but "today" for trips is the company's local
date (BUSINESS_TIMEZONE, Europe/Kyiv): a trip that ends on the 17th is completed on the 18th in
Kyiv, not at 22:00 / 21:00 UTC. zoneinfo needs the `tzdata` package on Windows."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.config import settings


def today(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(ZoneInfo(settings.business_timezone)).date()
