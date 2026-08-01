from functools import wraps

from .enums import AccountStatus
from .exceptions import AccountClosedError, AccountFrozenError


def account_must_be_active(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.status != AccountStatus.ACTIVE.value:
            if self.status == AccountStatus.FROZEN.value:
                raise AccountFrozenError()
            else:
                raise AccountClosedError()

        return func(self, *args, **kwargs)

    return wrapper
