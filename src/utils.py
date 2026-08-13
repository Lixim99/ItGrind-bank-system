from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from pwdlib import PasswordHash

BANK_TIMEZONE = ZoneInfo("Europe/Moscow")
Clock = Callable[[], datetime]

password_hasher = PasswordHash.recommended()


def bank_now() -> datetime:
    return datetime.now(BANK_TIMEZONE)


def to_bank_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime must be timezone-aware")

    return value.astimezone(BANK_TIMEZONE)
