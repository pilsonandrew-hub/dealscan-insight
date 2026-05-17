"""Time parsing helpers for DealerScope ingest.

Extracted from the Apify ingest router without behavior changes so auction end
normalization can be tested independently of FastAPI/Supabase wiring.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional


def parse_datetime_utc(raw_value) -> Optional[datetime]:
    """Parse a datetime-like value and normalize it to UTC.

    Preserves the legacy router behavior:
    - None/empty values return None
    - naive datetimes are treated as UTC
    - ISO strings may use trailing Z
    - unparsable strings return None
    """
    if raw_value in {None, ""}:
        return None
    if isinstance(raw_value, datetime):
        dt = raw_value
    else:
        text = str(raw_value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_auction_end_time(raw_value, *, reference_dt: Optional[datetime] = None) -> Optional[str]:
    """Normalize absolute or countdown auction-end values to UTC ISO strings."""
    if raw_value in {None, ""}:
        return None
    if isinstance(raw_value, datetime):
        dt = parse_datetime_utc(raw_value)
        return dt.isoformat() if dt else None

    text = str(raw_value).strip()
    if not text:
        return None

    parsed_absolute = parse_datetime_utc(text)
    if parsed_absolute:
        return parsed_absolute.isoformat()

    lower_text = text.lower()
    total_delta = timedelta(0)
    matched = False

    # Handle HH:MM:SS or MM:SS countdown format (e.g. "12:34:56" or "45:00")
    hms_match = re.fullmatch(r"(\d+):(\d{2}):(\d{2})", text.strip())
    ms_match = re.fullmatch(r"(\d+):(\d{2})", text.strip()) if not hms_match else None
    if hms_match:
        h, m, s = int(hms_match.group(1)), int(hms_match.group(2)), int(hms_match.group(3))
        total_delta = timedelta(hours=h, minutes=m, seconds=s)
        matched = True
    elif ms_match:
        m, s = int(ms_match.group(1)), int(ms_match.group(2))
        total_delta = timedelta(minutes=m, seconds=s)
        matched = True
    else:
        # Spelled-out and compact relative formats:
        # "2 days 4 hours", "1d 2h", "45 minutes", "45m", "3 hrs"
        for pattern, unit in (
            (r"(\d+)\s*d(?:ay(?:s)?)?\b", "days"),
            (r"(\d+)\s*(?:hour|hr|hrs|h)\b", "hours"),
            (r"(\d+)\s*(?:min(?:ute)?(?:s)?|m)\b", "minutes"),
        ):
            match = re.search(pattern, lower_text)
            if match:
                matched = True
                total_delta += timedelta(**{unit: int(match.group(1))})

    if matched:
        anchor = reference_dt or datetime.now(timezone.utc)
        return (anchor + total_delta).astimezone(timezone.utc).isoformat()

    return None
