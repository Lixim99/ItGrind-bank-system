from .exceptions import InvalidOperationError
from .utils import bank_now, to_bank_time


class OperationPolicy:
    @staticmethod
    def ensure_operation_allowed() -> None:
        current_time = to_bank_time(bank_now())

        if 0 <= current_time.hour < 5:
            raise InvalidOperationError(
                "Operations are prohibited from 00:00 to 05:00"
            )
