from functools import wraps

from .enums import AccountStatus
from .exceptions import (
    AccountClosedError,
    AccountFrozenError,
    InvalidOperationError,
)


def account_must_be_active(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.client is None:
            raise InvalidOperationError("Account has no registered client.")
        if self.client.is_blocked:
            raise InvalidOperationError(
                "A blocked client cannot perform financial operations."
            )

        if self.status != AccountStatus.ACTIVE:
            if self.status == AccountStatus.FROZEN:
                raise AccountFrozenError()
            raise AccountClosedError()

        return func(self, *args, **kwargs)

    return wrapper
