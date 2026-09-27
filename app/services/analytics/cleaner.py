"""Validation and standardization layer converting raw Wikimedia DTOs to clean continuous DataFrames."""

from __future__ import annotations

from datetime import datetime
from typing import List
import pandas as pd

from app.schemas.requests import PageviewItem
from app.services.wikimedia.utils import format_period_label


def parse_boundary_date(date_str: str) -> datetime:
    """Parse YYYYMMDD or YYYY-MM-DD or YYYYMMDD00 into a Python datetime object."""
    cleaned = date_str.replace("-", "").strip()[:8]
    return datetime.strptime(cleaned, "%Y%m%d")


def standardize_pageviews_to_dataframe(
    items: List[PageviewItem],
    start_date: str,
    end_date: str,
    granularity: str = "monthly",
) -> pd.DataFrame:
    """Transform PageviewItem records into a gap-free, continuous pandas DataFrame."""
    start_dt = parse_boundary_date(start_date)
    end_dt = parse_boundary_date(end_date)

    freq = "MS" if granularity.lower() == "monthly" else "D"

    if granularity.lower() == "monthly":
        start_grid = datetime(start_dt.year, start_dt.month, 1)
        end_grid = datetime(end_dt.year, end_dt.month, 1)
    else:
        start_grid = start_dt
        end_grid = end_dt

    date_grid = pd.date_range(start=start_grid, end=end_grid, freq=freq)

    if not items:
        rows = []
        for dt in date_grid:
            ts = dt.strftime("%Y%m%d00")
            date_label = format_period_label(ts, granularity=granularity)
            rows.append({
                "datetime": dt,
                "timestamp": ts,
                "date": date_label,
                "views": 0,
                "is_partial": False,
            })
        df = pd.DataFrame(rows)
        df.set_index("datetime", inplace=True)
        return df

    records = []
    for item in items:
        clean_ts = item.timestamp[:8] if len(item.timestamp) >= 8 else item.timestamp
        try:
            dt = datetime.strptime(clean_ts, "%Y%m%d")
            if granularity.lower() == "monthly":
                dt = datetime(dt.year, dt.month, 1)
        except Exception:
            dt = parse_boundary_date(item.date)

        records.append({
            "datetime": dt,
            "timestamp": item.timestamp,
            "date": item.date,
            "views": int(item.views),
            "is_partial": bool(item.is_partial),
        })

    raw_df = pd.DataFrame(records)
    raw_df = raw_df.groupby("datetime", as_index=False).agg({
        "timestamp": "last",
        "date": "last",
        "views": "sum",
        "is_partial": "max",
    })
    raw_df.set_index("datetime", inplace=True)

    full_df = raw_df.reindex(date_grid)
    full_df["views"] = full_df["views"].fillna(0).astype(int)
    full_df["is_partial"] = full_df["is_partial"].fillna(False).astype(bool)

    for dt, row in full_df.iterrows():
        if pd.isna(row["timestamp"]) or not row["timestamp"]:
            ts = dt.strftime("%Y%m%d00")
            full_df.at[dt, "timestamp"] = ts
            full_df.at[dt, "date"] = format_period_label(ts, granularity=granularity)

    full_df.sort_index(inplace=True)
    return full_df
