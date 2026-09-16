import pytest

from actblue_refunds.cli import parse_args, rolling_window


def test_rolling_window_spans_exactly_the_requested_months():
    start, end = rolling_window(6, today="2026-08-26")
    assert start == "2026-02-27"
    assert end == "2026-08-27"


def test_rolling_window_handles_month_end_without_crashing():
    # end becomes 2026-08-31; minus 6 months would be "Feb 31", which doesn't
    # exist. Naive date(year, month - 6, day) arithmetic raises ValueError
    # here - DateOffset must clamp to Feb 28 instead.
    start, end = rolling_window(6, today="2026-08-30")
    assert start == "2026-02-28"
    assert end == "2026-08-31"


def test_rolling_window_crosses_year_boundary():
    start, end = rolling_window(6, today="2026-01-15")
    assert start == "2025-07-16"
    assert end == "2026-01-16"


def test_parse_args_computes_start_end_from_months_back():
    args = parse_args(["--months-back", "6"])
    assert args.start is not None
    assert args.end is not None


def test_parse_args_rejects_months_back_combined_with_explicit_dates():
    with pytest.raises(SystemExit):
        parse_args(["--months-back", "6", "--start", "2026-01-01"])


def test_parse_args_requires_dates_or_months_back():
    with pytest.raises(SystemExit):
        parse_args([])


def test_parse_args_accepts_explicit_start_end_as_before():
    args = parse_args(["--start", "2026-01-01", "--end", "2026-02-01"])
    assert args.start == "2026-01-01"
    assert args.end == "2026-02-01"
