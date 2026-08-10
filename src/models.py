from abc import ABC, abstractmethod
from decimal import Decimal
from typing import ClassVar, Self, TypeVar
from uuid import UUID, uuid4

from pwdlib import PasswordHash
from sqlalchemy import (
    Boolean,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Uuid,
    or_,
    select,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, validates

from .base import Base
from .enums import (
    AccountCurrency,
    AccountStatus,
    ClientStatus,
    InvestmentAccountActives,
)
from .exceptions import InsufficientFundsError, InvalidOperationError
from .utils import account_must_be_active


class AbstractAccount(ABC):
    @property
    def id(self) -> str:
        return self._id

    @property
    def client(self) -> str:
        return self._client

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


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id"),
        nullable=False,
        index=True,
    )

    currency: Mapped[AccountCurrency] = mapped_column(
        SqlEnum(
            AccountCurrency,
            name="currency",
        ),
        nullable=False,
    )

    status: Mapped[AccountStatus] = mapped_column(
        SqlEnum(
            AccountStatus,
            name="status",
        ),
        nullable=False,
    )

    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    account_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    client: Mapped["Client"] = relationship(
        "Client",
        back_populates="accounts",
    )

    withdrawal_limit: ClassVar[Decimal] = Decimal("1000.00")
    max_overdraft_limit: ClassVar[Decimal] = Decimal("0.00")
    withdrawal_commission: ClassVar[Decimal] = Decimal("0.01")

    __mapper_args__ = {
        "polymorphic_on": account_type,
        "polymorphic_identity": "bank_account",
    }

    def __init__(
        self,
        *,
        client: "Client",
        currency: AccountCurrency | str,
    ) -> None:
        self.client = client
        self.currency = AccountCurrency(currency)
        self.status = AccountStatus.ACTIVE
        self.balance = Decimal("0.00")

    @account_must_be_active
    def deposit(self, amount: Decimal | int | float) -> None:
        amount = self._as_decimal(amount)
        if amount <= 0:
            raise InvalidOperationError("Deposit amount must be positive.")

        self.balance += amount

    @account_must_be_active
    def withdraw(self, amount: Decimal | int | float) -> None:
        amount = self._as_decimal(amount)
        if amount <= 0:
            raise InvalidOperationError("Withdrawal amount must be positive.")

        amount_with_commission = amount + (amount * self.withdrawal_commission)

        if self.balance + self.max_overdraft_limit < amount_with_commission:
            raise InsufficientFundsError()

        if amount_with_commission > self.withdrawal_limit:
            raise InvalidOperationError(
                f"Withdrawal amount exceeds the limit of {self.withdrawal_limit}.")

        self.balance -= amount_with_commission

    def change_account_status(self, status: AccountStatus | str) -> None:
        self.status = AccountStatus(status)

    @staticmethod
    def _as_decimal(amount: float) -> Decimal:
        if isinstance(amount, bool) or not isinstance(
            amount,
            (Decimal, int, float),
        ):
            raise TypeError("Amount must be a number")

        normalized = Decimal(str(amount))

        if not normalized.is_finite():
            raise ValueError("Amount must be finite")

        return normalized

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
            f"ID: ***{str(self.id)[-4:]}, "
            f"Client: {self.client}, "
            f"Status: {self.status}, "
            f"Currency: {self.currency}, "
            f"Balance: {self.balance}"
            f")"
        )


class SavingsAccount(BankAccount):
    __mapper_args__ = {"polymorphic_identity": "savings_account"}

    min_balance: ClassVar[Decimal] = Decimal("100.00")
    monthly_interest_rate: ClassVar[Decimal] = Decimal("0.05")

    @account_must_be_active
    def apply_monthly_interest(self) -> None:
        if self.balance < self.min_balance:
            raise InvalidOperationError(
                "Balance is below the minimum required for interest application.")

        self.balance += self.balance * self.monthly_interest_rate

    @account_must_be_active
    def withdraw(self, amount: float) -> None:
        normalized_amount = self._as_decimal(amount)
        amount_with_commission = normalized_amount
        if normalized_amount > 0:
            amount_with_commission += (
                normalized_amount * self.withdrawal_commission
            )

        if self.balance - amount_with_commission < self.min_balance:
            raise InvalidOperationError(
                f"Withdrawal would reduce the balance below {self.min_balance}.")

        super().withdraw(normalized_amount)

    def get_account_info(self) -> dict:
        return {
            **super().get_account_info(),
            "Minimum Balance": self.min_balance,
            "Monthly Interest Rate": self.monthly_interest_rate
        }

    def __str__(self) -> str:
        return super().__str__().replace("BankAccount", "SavingsAccount", 1)


class PremiumAccount(BankAccount):
    __mapper_args__ = {"polymorphic_identity": "premium_account"}

    withdrawal_limit: ClassVar[Decimal] = Decimal("5000.00")
    max_overdraft_limit: ClassVar[Decimal] = Decimal("1000.00")
    fixed_withdrawal_commission: ClassVar[Decimal] = Decimal("1.00")
    withdrawal_commission: ClassVar[Decimal] = Decimal("0.00")

    def get_account_info(self) -> dict:
        return {
            **super().get_account_info(),
            "Withdrawal Limit": self.withdrawal_limit,
            "Maximum Overdraft Limit": self.max_overdraft_limit,
            "Fixed Commission": self.fixed_withdrawal_commission
        }

    @account_must_be_active
    def withdraw(self, amount: float) -> None:
        normalized_amount = self._as_decimal(amount)
        if normalized_amount > 0:
            normalized_amount += self.fixed_withdrawal_commission

        super().withdraw(normalized_amount)

    def __str__(self) -> str:
        return super().__str__().replace("BankAccount", "PremiumAccount", 1)


class InvestmentAccount(BankAccount):
    __mapper_args__ = {"polymorphic_identity": "investment_account"}

    yearly_growth_rate: ClassVar[Decimal] = Decimal("0.13")

    @account_must_be_active
    def project_yearly_growth(self) -> None:
        if self.balance <= 0:
            raise InvalidOperationError(
                "Balance must be positive to project yearly growth.")

        self.balance *= Decimal("1.00") + self.yearly_growth_rate

    def get_account_info(self) -> dict:
        return {
            **super().get_account_info(),
            "Yearly Growth Rate": self.yearly_growth_rate,
            "ACTIVES": [active.value for active in InvestmentAccountActives]
        }

    def withdraw(self, amount: float) -> None:
        super().withdraw(amount)

    def __str__(self) -> str:
        return super().__str__().replace("BankAccount", "InvestmentAccount", 1)


AccountT = TypeVar("AccountT", bound=BankAccount)

password_hasher = PasswordHash.recommended()


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    phone: Mapped[str] = mapped_column(
        String(16),
        unique=True,
        nullable=False,
    )

    age: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    is_suspicious: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    failed_login_attempts: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
    )

    email: Mapped[str] = mapped_column(
        String(254),
        unique=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ClientStatus.ACTIVE.value,
    )

    first_name: Mapped[str] = mapped_column(String(100))

    last_name: Mapped[str] = mapped_column(String(100))

    middle_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    accounts: Mapped[list[BankAccount]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )

    @validates("age")
    def _validate_age(self, _key: str, age: int) -> int:
        if isinstance(age, bool) or not isinstance(age, int):
            raise TypeError("Age must be an integer")
        if age < 18:
            raise ValueError("Client must be at least 18 years old")
        return age

    @validates("first_name", "last_name", "email", "phone")
    def _validate_required_text(self, key: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            readable_name = key.replace("_", " ").capitalize()
            raise ValueError(f"{readable_name} is required")

        normalized = value.strip()
        if key == "email":
            normalized = normalized.lower()
        return normalized

    @property
    def is_blocked(self) -> bool:
        return self.status == ClientStatus.BLOCKED.value

    @property
    def full_name(self) -> str:
        return " ".join(
            part
            for part in (self.last_name, self.first_name, self.middle_name)
            if part
        )

    @property
    def contacts(self) -> dict[str, str]:
        return {"email": self.email, "phone": self.phone}

    @property
    def account_numbers(self) -> list[str]:
        return [str(account.id) for account in self.accounts]

    @classmethod
    def create(
        cls,
        *,
        age: int,
        first_name: str,
        last_name: str,
        middle_name: str | None = None,
        email: str,
        phone: str,
        password: str
    ) -> Self:
        if age < 18:
            raise ValueError("Too young")

        return cls(
            id=uuid4(),
            age=age,
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            email=email,
            phone=phone,
            password_hash=password_hasher.hash(password),
            status=ClientStatus.ACTIVE.value,
            failed_login_attempts=0,
            is_suspicious=False,
        )

    def register_failed_login(self, max_attempts: int) -> None:
        self.failed_login_attempts = (self.failed_login_attempts or 0) + 1
        if self.failed_login_attempts >= max_attempts:
            self.status = ClientStatus.BLOCKED.value
            self.is_suspicious = True

    def reset_failed_logins(self) -> None:
        self.failed_login_attempts = 0


class Bank:
    MAX_FAILED_LOGIN_ATTEMPTS = 3

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_client(self, client: Client) -> None:
        duplicate = self._session.scalar(
            select(Client).where(
                or_(Client.phone == client.phone, Client.email == client.email)
            )
        )

        if duplicate is not None:
            raise ValueError(
                "A client with this phone or email already exists")

        self._session.add(client)
        self._session.flush()

    def authenticate_client(self, phone: str, password: str) -> Client | None:
        client = self._session.scalar(
            select(Client).where(Client.phone == phone))

        if client is None:
            return None

        if client.is_blocked:
            return None

        is_password_correct = password_hasher.verify(
            password,
            client.password_hash,
        )

        if not is_password_correct:
            client.register_failed_login(self.MAX_FAILED_LOGIN_ATTEMPTS)
            self._session.flush()
            return None

        client.reset_failed_logins()
        self._session.flush()
        return client

    def save_account_transact(self, account: BankAccount) -> None:
        managed_account = self._get_account(account)
        self._ensure_client_can_transact(managed_account.client)
        self._session.flush()

    def open_account(self, account: AccountT) -> AccountT:
        managed_client = self._get_client(account.client)
        self._ensure_client_can_transact(managed_client)
        account.client = managed_client
        self._session.add(account)
        self._session.flush()

        return account

    def close_account(self, account: BankAccount) -> None:
        managed_account = self._get_account(account)
        self._ensure_client_can_transact(managed_account.client)
        if managed_account.status == AccountStatus.CLOSED:
            raise InvalidOperationError("Account is already closed.")

        managed_account.change_account_status(AccountStatus.CLOSED)
        self._session.flush()

    def search_accounts(
        self,
        *,
        currency: AccountCurrency | None = None,
        client: Client | None = None,
    ) -> list[BankAccount]:
        statement = select(BankAccount)

        if currency is not None:
            statement = statement.where(BankAccount.currency == currency)

        if client is not None:
            statement = statement.where(BankAccount.client_id == client.id)

        accounts = list(self._session.scalars(statement))
        # _bind_account_security
        return accounts

    def freeze_account(self, account: BankAccount) -> None:
        managed_account = self._get_account(account)
        self._ensure_client_can_transact(managed_account.client)
        if managed_account.status != AccountStatus.ACTIVE:
            raise InvalidOperationError(
                "Only an active account can be frozen.")

        managed_account.change_account_status(AccountStatus.FROZEN)
        self._session.flush()

    def unfreeze_account(self, account: BankAccount) -> None:
        managed_account = self._get_account(account)
        self._ensure_client_can_transact(managed_account.client)
        if managed_account.status != AccountStatus.FROZEN:
            raise InvalidOperationError(
                "Only a frozen account can be unfrozen.")

        managed_account.change_account_status(AccountStatus.ACTIVE)
        self._session.flush()

    def get_total_balance(
        self,
        currency: AccountCurrency,
        client: Client | None = None
    ) -> Decimal:
        accounts = self.search_accounts(client=client, currency=currency)

        return sum(
            (account.balance for account in accounts),
            start=Decimal("0.00"),
        )

    def get_clients_ranking(self, currency: AccountCurrency) -> list[Client]:
        clients = list(
            self._session.scalars(
                select(Client).order_by(Client.last_name,
                                        Client.first_name, Client.id)
            )
        )

        return sorted(
            clients,
            key=lambda client: self.get_total_balance(currency, client),
            reverse=True,
        )

    def _get_account(self, account: BankAccount) -> BankAccount:
        if account.id is None:
            raise ValueError("Account does not belong to this bank")

        managed_account = self._session.get(BankAccount, account.id)

        if managed_account is None:
            raise ValueError("Account does not belong to this bank")

        # self._bind_account_security(managed_account)

        return managed_account

    def _get_client(self, client: Client) -> Client:
        if client.id is None:
            raise ValueError("Client does not belong to this bank")

        with self._session.no_autoflush:
            managed_client = self._session.get(Client, client.id)
        if managed_client is None:
            raise ValueError("Client does not belong to this bank")

        return managed_client

    @staticmethod
    def _ensure_client_can_transact(client: Client | None) -> None:
        if client is None:
            raise InvalidOperationError("Account has no registered client.")
        if client.is_blocked:
            raise InvalidOperationError(
                "A blocked client cannot perform financial operations."
            )
