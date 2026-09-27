"""Pure formatting and date utility functions for Wikimedia APIs."""

from __future__ import annotations

import calendar
from datetime import datetime


WIKIMEDIA_MIN_DATE = "2015070100"


def format_date_for_pageviews(date_str: str) -> str:
    """Format a date string (YYYY-MM-DD or YYYYMMDD) into Wikimedia API format (YYYYMMDD00)."""
    cleaned = date_str.replace("-", "").strip()
    if len(cleaned) == 8:
        return f"{cleaned}00"
    if len(cleaned) == 10:
        return cleaned
    return cleaned


def align_date_for_pageviews(
    date_str: str,
    is_end: bool = False,
    granularity: str = "monthly",
) -> str:
    """Align date string to valid Wikimedia Pageviews API boundaries.

    For monthly granularity:
      - Wikimedia API strictly requires start dates to be the 1st of a month (YYYYMM0100).
      - Wikimedia API strictly requires end dates to be either 01 or the last day of the month (e.g. 28, 30, 31).
      - If an arbitrary mid-month day is provided, it is safely clamped to prevent 400 Bad Request errors.
    """
    cleaned = date_str.replace("-", "").strip()
    if len(cleaned) < 8:
        return f"{cleaned}00" if len(cleaned) == 8 else cleaned

    year = int(cleaned[:4])
    month = int(cleaned[4:6])
    day = int(cleaned[6:8])

    if granularity.lower() == "monthly":
        _, last_day = calendar.monthrange(year, month)
        if not is_end:
            return f"{year:04d}{month:02d}0100"

        if day == 1 or day == last_day:
            return f"{year:04d}{month:02d}{day:02d}00"

        now = datetime.now()
        if year == now.year and month == now.month:
            clamped_day = min(day, now.day)
            return f"{year:04d}{month:02d}{clamped_day:02d}00"
        return f"{year:04d}{month:02d}{last_day:02d}00"

    return f"{cleaned[:8]}00"


def format_period_label(raw_ts: str, granularity: str = "monthly") -> str:
    """Format raw Wikimedia timestamp (e.g. '2023010100') into human-readable date ('2023-01' or '2023-01-01')."""
    if len(raw_ts) >= 8:
        year = raw_ts[:4]
        month = raw_ts[4:6]
        day = raw_ts[6:8]
        if granularity.lower() == "monthly":
            return f"{year}-{month}"
        return f"{year}-{month}-{day}"
    return raw_ts


def is_current_period(raw_ts: str, granularity: str = "monthly") -> bool:
    """Check if a Wikimedia timestamp corresponds to the current ongoing period (month or day)."""
    now = datetime.now()
    current_year_month = now.strftime("%Y%m")
    current_year_month_day = now.strftime("%Y%m%d")
    if granularity.lower() == "monthly":
        return raw_ts.startswith(current_year_month)
    return raw_ts.startswith(current_year_month_day)
