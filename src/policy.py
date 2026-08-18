from datetime import datetime

from .exceptions import InvalidOperationError
from .utils import bank_now, to_bank_time


class OperationPolicy:
    @staticmethod
    def ensure_operation_allowed(
        operation_time: datetime | None = None,
    ) -> None:
        if operation_time is None:
            operation_time = bank_now()

        current_time = to_bank_time(operation_time)

        if 0 <= current_time.hour < 5:
            raise InvalidOperationError(
                "Operations are prohibited from 00:00 to 05:00"
            )
