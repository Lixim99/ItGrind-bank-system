from datetime import datetime, timezone

import pytest

from src.utils import BANK_TIMEZONE, bank_now, to_bank_time


def test_bank_now_returns_moscow_time():
    current_time = bank_now()

    assert current_time.tzinfo == BANK_TIMEZONE
    assert current_time.utcoffset() is not None


def test_to_bank_time_converts_aware_datetime():
    utc_time = datetime(2025, 12, 31, 22, tzinfo=timezone.utc)

    result = to_bank_time(utc_time)

    assert result == datetime(2026, 1, 1, 1, tzinfo=BANK_TIMEZONE)
    assert result.tzinfo == BANK_TIMEZONE


def test_to_bank_time_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        to_bank_time(datetime(2026, 1, 1, 12))
