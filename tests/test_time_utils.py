from datetime import datetime, timezone

import pytest

from src.exceptions import InvalidOperationError
from src.policy import OperationPolicy
from src.utils import BANK_TIMEZONE, bank_now, to_bank_time


def test_bank_now_returns_timezone_aware_moscow_time():
    current_time = bank_now()

    assert current_time.tzinfo == BANK_TIMEZONE
    assert current_time.utcoffset() is not None


def test_to_bank_time_converts_aware_datetime():
    utc_time = datetime(2025, 12, 31, 22, tzinfo=timezone.utc)

    assert to_bank_time(utc_time) == datetime(
        2026,
        1,
        1,
        1,
        tzinfo=BANK_TIMEZONE,
    )


def test_to_bank_time_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        to_bank_time(datetime(2026, 1, 1, 12))


@pytest.mark.parametrize("hour", [0, 1, 4])
def test_day3_operation_policy_blocks_from_midnight_until_five(
    bank_clock,
    hour,
):
    bank_clock.now = datetime(
        2026,
        1,
        1,
        hour,
        59,
        tzinfo=BANK_TIMEZONE,
    )

    with pytest.raises(InvalidOperationError, match="00:00 to 05:00"):
        OperationPolicy.ensure_operation_allowed()


def test_day3_operation_policy_allows_operation_at_exactly_five(bank_clock):
    bank_clock.now = datetime(
        2026,
        1,
        1,
        5,
        tzinfo=BANK_TIMEZONE,
    )

    OperationPolicy.ensure_operation_allowed()
