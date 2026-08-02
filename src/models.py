from abc import ABC, abstractmethod
from uuid import uuid4

from .enums import AccountStatus, Currency, InvestmentAccountActives
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
    _withdrawal_limit: float = 1000.0
    _max_overdraft_limit: float = 0.0
    _withdrawal_comission: float = 0.01

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

        amount_with_cummission = amount + (amount * self._withdrawal_comission)

        if self._balance + self._max_overdraft_limit < amount_with_cummission:
            raise InsufficientFundsError()

        if amount_with_cummission > self._withdrawal_limit:
            raise InvalidOperationError(
                f"Withdrawal amount exceeds the limit of {self._withdrawal_limit}.")

        self._balance -= amount_with_cummission

    def get_account_info(self) -> dict:
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


class SavingsAccount(BankAccount):
    _min_balance: float = 100.0
    _monthly_interest_rate: float = 0.05

    def apply_monthly_interest(self):
        if (self._balance < self._min_balance):
            raise InvalidOperationError(
                "Balance is below the minimum required for interest application.")

        self._balance += self._balance * self._monthly_interest_rate

    def withdraw(self, amount: float):
        if amount > 0:
            amount_with_commission = amount + \
                (amount * self._withdrawal_comission)
        else:
            amount_with_commission = amount

        if self._balance - amount_with_commission < self._min_balance:
            raise InvalidOperationError(
                f"Withdrawal would reduce the balance below {self._min_balance}.")

        super().withdraw(amount)

    def get_account_info(self) -> dict:
        return {
            **super().get_account_info(),
            "Minimum Balance": self._min_balance,
            "Monthly Interest Rate": self._monthly_interest_rate
        }

    def __str__(self):
        return (
            f"SavingsAccount("
            f"ID: ***{self._id[-4:]}, "
            f"Owner: {self._owner}, "
            f"Status: {self._status}, "
            f"Currency: {self._currency}, "
            f"Balance: {self._balance}"
            f")"
        )


class PremiumAccount(BankAccount):
    _withdrawal_limit: float = 5000.0
    _max_overdraft_limit: float = 1000.0
    _fixed_withdrawal_commission: float = 1
    _withdrawal_comission: float = 0.0

    def get_account_info(self) -> dict:
        return {
            **super().get_account_info(),
            "Withdrawal Limit": self._withdrawal_limit,
            "Maximum Overdraft Limit": self._max_overdraft_limit,
            "Fixed Commission": self._fixed_withdrawal_commission
        }

    def withdraw(self, amount: float) -> None:
        if amount > 0:
            amount_with_fixed_cummision = amount + self._fixed_withdrawal_commission
        else:
            amount_with_fixed_cummision = amount

        super().withdraw(amount_with_fixed_cummision)

    def __str__(self):
        return (
            f"PremiumAccount("
            f"ID: ***{self._id[-4:]}, "
            f"Owner: {self._owner}, "
            f"Status: {self._status}, "
            f"Currency: {self._currency}, "
            f"Balance: {self._balance}"
            f")"
        )


class InvestmentAccount(BankAccount):
    _yearly_growth_rate: float = 0.13

    def project_yearly_growth(self) -> None:
        if self._balance <= 0:
            raise InvalidOperationError(
                "Balance must be positive to project yearly growth.")

        self._balance *= (1 + self._yearly_growth_rate)

    def get_account_info(self) -> dict:
        return {
            **super().get_account_info(),
            "Yearly Growth Rate": self._yearly_growth_rate,
            "ACTIVES": [active.value for active in InvestmentAccountActives]
        }

    def withdraw(self, amount: float) -> None:
        super().withdraw(amount)

    def __str__(self):
        return (
            f"InvestmentAccount("
            f"ID: ***{self._id[-4:]}, "
            f"Owner: {self._owner}, "
            f"Status: {self._status}, "
            f"Currency: {self._currency}, "
            f"Balance: {self._balance}"
            f")"
        )
