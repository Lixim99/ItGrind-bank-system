from abc import ABC, abstractmethod
from uuid import uuid4

from .enums import AccountStatus, Currency
from .exceptions import InsufficientFundsError, InvalidOperationError
from .utils import account_must_be_active


class AbstractAccount(ABC):
    @property
    def id(self) -> str:
        return self._id

    @property
    def owner(self) -> str:
        return self._owner

    @property
    def status(self) -> str:
        return self._status

    @property
    def balance(self) -> float:
        return self._balance

    @abstractmethod
    def deposit(self, amount: float) -> None:
        pass

    @abstractmethod
    def withdraw(self, amount: float) -> None:
        pass

    @abstractmethod
    def get_account_info(self) -> dict:
        pass


class BankAccount(AbstractAccount):
    @property
    def currency(self) -> str:
        return self._currency

    def __init__(self, owner: str, currency: str, status: AccountStatus = AccountStatus.ACTIVE.value):
        owner = owner.strip()

        if not owner:
            raise InvalidOperationError("Owner name cannot be empty.")

        self._id = str(uuid4())
        self._status = AccountStatus(status).value
        self._currency = Currency(currency).value
        self._owner = owner
        self._balance = 0.0

    @account_must_be_active
    def deposit(self, amount: float):
        if amount <= 0:
            raise InvalidOperationError("Deposit amount must be positive.")

        self._balance += amount

    @account_must_be_active
    def withdraw(self, amount: float):
        if amount <= 0:
            raise InvalidOperationError("Withdrawal amount must be positive.")

        if amount > self._balance:
            raise InsufficientFundsError()

        self._balance -= amount

    def get_account_info(self):
        return {
            "owner": self._owner,
            "status": self._status,
            "currency": self._currency,
            "balance": self._balance
        }

    def __str__(self):
        return (
            f"BankAccount("
            f"ID: ***{self._id[-4:]}, "
            f"Owner: {self._owner}, "
            f"Status: {self._status}, "
            f"Currency: {self._currency}, "
            f"Balance: {self._balance}"
            f")"
        )
