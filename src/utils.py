from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from pwdlib import PasswordHash

BANK_TIMEZONE = ZoneInfo("Europe/Moscow")
Clock = Callable[[], datetime]

password_hasher = PasswordHash.recommended()
MONEY_QUANTUM = Decimal("0.01")


def bank_now() -> datetime:
    return datetime.now(BANK_TIMEZONE)


def to_bank_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime must be timezone-aware")

    return value.astimezone(BANK_TIMEZONE)


def round_money(value: Decimal) -> Decimal:
    """Округлить банковскую сумму до двух знаков."""
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
