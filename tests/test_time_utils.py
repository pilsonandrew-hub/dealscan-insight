from datetime import datetime, timezone

from backend.ingest.time_utils import normalize_auction_end_time, parse_datetime_utc


def test_parse_datetime_utc_handles_z_suffix_and_naive_datetime_as_utc():
    assert parse_datetime_utc("2026-03-26T18:00:00.000Z").isoformat() == "2026-03-26T18:00:00+00:00"
    assert parse_datetime_utc(datetime(2026, 3, 26, 18, 0)).isoformat() == "2026-03-26T18:00:00+00:00"


def test_parse_datetime_utc_returns_none_for_empty_or_unparseable_values():
    assert parse_datetime_utc(None) is None
    assert parse_datetime_utc("") is None
    assert parse_datetime_utc("not-a-date") is None


def test_normalize_auction_end_time_handles_absolute_and_relative_formats():
    reference = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)

    assert normalize_auction_end_time("2026-03-26T18:00:00.000Z") == "2026-03-26T18:00:00+00:00"
    assert normalize_auction_end_time("1d 2h", reference_dt=reference) == "2026-04-04T14:00:00+00:00"
    assert normalize_auction_end_time("45:00", reference_dt=reference) == "2026-04-03T12:45:00+00:00"
    assert normalize_auction_end_time("01:02:03", reference_dt=reference) == "2026-04-03T13:02:03+00:00"
