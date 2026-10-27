"""Timestamp parsing shared by the API client and the analysis tabs."""

from __future__ import annotations

import datetime


def parse_timestamp_utc(ts) -> datetime.datetime | None:
    """Parse a Unix epoch (number or numeric string) or an ISO 8601 string.

    Returns a timezone-aware UTC datetime, or None if the value can't be parsed.
    Naive ISO strings are assumed to be UTC.
    """
    if ts is None or isinstance(ts, bool):
        return None
    if isinstance(ts, str):
        ts = ts.strip()
        try:
            ts = float(ts)
        except ValueError:
            try:
                dt = datetime.datetime.fromisoformat(ts.rstrip('Z'))
            except ValueError:
                return None
            if dt.tzinfo is None:
                return dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone(datetime.timezone.utc)
    if isinstance(ts, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None
