from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from .enums import (
    AccountCurrency,
    AccountStatus,
    ClientStatus,
    InvestmentAccountActives,
)
from .exceptions import (
    AccountClosedError,
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)
from .utils import bank_now, password_hasher


class AbstractAccount(ABC):
    @property
    def id(self) -> UUID:
        return self._id

    @property
    def client(self) -> "Client":
        return self._client

    @property
    def status(self) -> AccountStatus:
        return self._status

    @property
    def balance(self) -> Decimal:
        return self._balance

    @abstractmethod
    def deposit(self, amount: Decimal) -> None:
        ...

    @abstractmethod
    def withdraw(self, amount: Decimal) -> None:
        ...

    @abstractmethod
    def get_account_info(self) -> dict:
        ...


class BankAccount(AbstractAccount):
    @property
    def currency(self) -> AccountCurrency:
        return self._currency

    @property
    def account_type(self) -> str:
        return self._account_type

    @property
    def balance_history(self) -> tuple[tuple[datetime, Decimal], ...]:
        return tuple(self._balance_history)

    WITHDRAWAL_COMMISSION = Decimal("0.01")

    def __init__(
        self,
        *,
        client: "Client",
        currency: AccountCurrency,
    ) -> None:
        self._id = uuid4()
        self._client = client
        self._currency = AccountCurrency(currency)
        self._status = AccountStatus.ACTIVE
        self._balance = 0
        self._account_type = str(self.__class__)
        self._balance_history: list[
            tuple[datetime, Decimal]
        ] = []

    def deposit(self, amount: Decimal) -> None:
        self._validate_amount(amount)
        self._ensure_can_operate()

        self._balance += amount
        self._record_balance()

    def withdraw(self, amount: Decimal) -> None:
        self._validate_amount(amount)
        self._ensure_can_operate()

        commission = self._calculate_commission(amount)
        total = amount + commission

        if self.balance < total:
            raise InsufficientFundsError(
                "Available balance is less than withdrawal total"
            )

        self._balance -= total
        self._record_balance()

    def debit(self, amount: Decimal) -> None:
        self._validate_amount(amount)
        self._ensure_can_operate()

        self._validate_debit(amount)
        self._balance -= amount
        self._record_balance()

    def change_account_status(self, status: AccountStatus) -> None:
        self._status = AccountStatus(status)

    def _calculate_commission(self, amount: Decimal) -> Decimal:
        return amount * self.WITHDRAWAL_COMMISSION

    def _validate_amount(self, amount: Decimal) -> None:
        if not amount.is_finite():
            raise InvalidOperationError("Amount must be finite")

        if amount <= 0:
            raise InvalidOperationError("Amount must be positive")

    def _validate_debit(self, amount: Decimal) -> None:
        balance_after = self.balance - amount

        if balance_after < 0:
            raise InsufficientFundsError(
                "Available balance is less than required debit"
            )

    def _ensure_can_operate(self) -> None:
        if self.status == AccountStatus.FROZEN:
            raise AccountFrozenError()

        if self.status == AccountStatus.CLOSED:
            raise AccountClosedError()

        if self.client.is_blocked:
            raise InvalidOperationError(
                'A blocked client cannot perform financial operations'
            )

    def _validate_status(self, status: AccountStatus):
        # сделать валидацию статуса
        ...

    def _restore_balance(self, balance: Decimal) -> None:
        self._balance = balance

    def _record_balance(self) -> None:
        self._balance_history.append(
            (
                bank_now(),
                self._balance,
            )
        )

    def get_account_info(self) -> dict:
        return {
            "client": self.client,
            "status": self.status,
            "currency": self.currency,
            "balance": self.balance
        }

    def __str__(self):
        return (
            f"BankAccount("
            f"Client: {self.client.first_name} {self.client.last_name}, "
            f"Status: {self.status.value}, "
            f"Account: ***{str(self.id)[-4:]}, "
            f"Currency: {self.currency}, "
            f"Balance: {self.balance}"
            f")"
        )


class SavingsAccount(BankAccount):
    MIN_BALANCE: Decimal = Decimal("100.00")
    MONTHLY_INTEREST_RATE: Decimal = Decimal("0.05")

    def apply_monthly_interest(self) -> None:
        self._ensure_can_operate()
        if self.balance < self.MIN_BALANCE:
            raise InvalidOperationError(
                "Balance is below the minimum required for interest application."
            )

        self._balance += self.balance * self.MONTHLY_INTEREST_RATE

    def withdraw(self, amount: Decimal) -> None:
        self._ensure_can_operate()
        self._validate_amount(amount)

        commission = self._calculate_commission(amount)

        balance_after = self.balance - amount - commission

        if balance_after < self.MIN_BALANCE:
            raise InvalidOperationError(
                f"Withdrawal would reduce the balance below {self.MIN_BALANCE}."
            )

        self._balance = balance_after
        self._record_balance()

    def _validate_debit(self, amount: Decimal) -> None:
        super()._validate_debit(amount)

        balance_after = self.balance - amount

        if balance_after < self.MIN_BALANCE:
            raise InvalidOperationError(
                f"Balance cannot be below {self.MIN_BALANCE}"
            )

    def get_account_info(self) -> dict:
        return {
            **super().get_account_info(),
            "Minimum Balance": self.MIN_BALANCE,
            "Monthly Interest Rate": self.MONTHLY_INTEREST_RATE
        }

    def __str__(self) -> str:
        return super().__str__().replace("BankAccount", "SavingsAccount", 1)


class PremiumAccount(BankAccount):
    WITHDRAWAL_LIMIT = Decimal(5000)
    OVERDRAFT_LIMIT = Decimal(1000)
    WITHDRAWAL_COMMISSION = Decimal(1)

    def get_account_info(self) -> dict:
        return {
            **super().get_account_info(),
            "Withdrawal Limit": self.WITHDRAWAL_LIMIT,
            "Maximum Overdraft Limit": self.OVERDRAFT_LIMIT,
            "Fixed Commission": self.WITHDRAWAL_COMMISSION
        }

    def _validate_debit(self, amount: Decimal) -> None:
        balance_after = self.balance - amount

        if balance_after < -self.OVERDRAFT_LIMIT:
            raise InsufficientFundsError(
                f"Debit would exceed the overdraft limit "
                f"of {self.OVERDRAFT_LIMIT}"
            )

    def withdraw(self, amount: Decimal) -> None:
        self._ensure_can_operate()
        self._validate_amount(amount)

        balance_after = self.balance - (amount + self.WITHDRAWAL_COMMISSION)

        if balance_after < -self.OVERDRAFT_LIMIT:
            raise InsufficientFundsError(
                "Withdrawal would exceed the overdraft limit"
            )

        self._balance = balance_after
        self._record_balance()

    def __str__(self) -> str:
        return super().__str__().replace("BankAccount", "PremiumAccount", 1)


class InvestmentAccount(BankAccount):
    YEARLY_GROWTH_RATE: Decimal = Decimal("0.13")

    def project_yearly_growth(self) -> None:
        self._ensure_can_operate()

        if self.balance <= 0:
            raise InvalidOperationError(
                "Balance must be positive to project yearly growth."
            )

        self._balance *= 1 + self.YEARLY_GROWTH_RATE

    def get_account_info(self) -> dict:
        return {
            **super().get_account_info(),
            "Yearly Growth Rate": self.YEARLY_GROWTH_RATE,
            "ACTIVES": [active.value for active in InvestmentAccountActives]
        }

    def withdraw(self, amount: Decimal) -> None:
        super().withdraw(amount)

    def __str__(self) -> str:
        return super().__str__().replace("BankAccount", "InvestmentAccount", 1)


class Client:
    def __init__(
        self,
        *,
        first_name: str,
        last_name: str,
        middle_name: str | None = None,
        phone: str,
        age: int,
        email: str,
        password: str,
    ) -> None:
        self._id = uuid4()
        self._first_name = self._validate_required_text(first_name)
        self._last_name = self._validate_required_text(last_name)
        self._middle_name = middle_name.strip() if middle_name is not None else ""
        self._phone = self._validate_phone(phone)
        self._age = self._validate_age(age)
        self._status = ClientStatus.ACTIVE
        self._is_suspicious = False
        self._failed_login_attempts = 0
        self._email = self._validate_email(email)
        self._password_hash = password_hasher.hash(password)
        self._accounts = []

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def first_name(self) -> str:
        return self._first_name

    @property
    def last_name(self) -> str:
        return self._last_name

    @property
    def middle_name(self) -> str:
        return self._middle_name

    @property
    def phone(self) -> str:
        return self._phone

    @property
    def age(self) -> int:
        return self._age

    @property
    def status(self) -> ClientStatus:
        return self._status

    @property
    def email(self) -> str:
        return self._email

    @property
    def password_hash(self) -> str:
        return self._password_hash

    @property
    def is_suspicious(self) -> bool:
        return self._is_suspicious

    @property
    def failed_login_attempts(self) -> int:
        return self._failed_login_attempts

    @property
    def accounts(self) -> list[BankAccount]:
        return self._accounts

    @property
    def is_blocked(self) -> bool:
        return self.status == ClientStatus.BLOCKED

    @property
    def contacts(self) -> dict[str, str]:
        return {"email": self.email, "phone": self.phone}

    @property
    def account_numbers(self) -> list[str]:
        return [str(account.id) for account in self.accounts]

    def add_account(self, account: BankAccount) -> None:
        self._accounts.append(account)

    def _validate_age(self, age: int) -> int:
        if age < 18:
            raise ValueError("Client must be at least 18 years old")

        return age

    def _validate_phone(self, phone: str) -> str:
        normalized_phone = phone.strip()

        if not normalized_phone:
            raise ValueError("Phone is required")

        if phone.startswith("+"):
            digits = phone[1:]
        else:
            digits = phone

        if not digits.isdigit():
            raise ValueError("Phone must contain only digits")

        if len(digits) < 10:
            raise ValueError("Phone number is too short")

        if len(digits) > 15:
            raise ValueError("Phone number is too long")

        return normalized_phone

    def _validate_email(self, email: str) -> str:
        normalized_email = email.strip().lower()

        if not normalized_email:
            raise ValueError("Email is required")

        if normalized_email.count("@") != 1:
            raise ValueError("Too many @")

        local_part, domain = email.split("@")

        if not local_part:
            raise ValueError("Email local part cannot be empty")

        if not domain:
            raise ValueError("Email domain cannot be empty")

        if "." not in domain:
            raise ValueError("Email domain must contain a dot")

        if domain.startswith(".") or domain.endswith("."):
            raise ValueError("Invalid email domain")

        return normalized_email

    def _validate_required_text(self, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("Field is required")

        return normalized

    def register_failed_login(self, max_attempts: int) -> None:
        self._failed_login_attempts = (self._failed_login_attempts or 0) + 1

        if self._failed_login_attempts >= max_attempts:
            self._status = ClientStatus.BLOCKED
            self._is_suspicious = True

    def reset_failed_logins(self) -> None:
        self._failed_login_attempts = 0
