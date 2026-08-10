import heapq
from datetime import datetime, timezone
from decimal import Decimal
from itertools import count
from typing import ClassVar
from uuid import UUID, uuid4

from .enums import (
    AccountCurrency,
    TransactionPriority,
    TransactionStatus,
    TransactionType,
)
from .exceptions import (
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)
from .models import BankAccount


class RetryableTransactionError(Exception):
    # RetryableTransactionError предназначен для временных технических
    # ошибок (например, timeout внешнего сервиса курсов валют).
    pass


class Transaction:
    @property
    def id(self) -> UUID:
        return self._id

    @property
    def amount(self) -> Decimal:
        return self._amount

    @property
    def currency_from(self) -> AccountCurrency:
        return self._currency_from

    @property
    def currency_to(self) -> AccountCurrency:
        return self._currency_to

    @property
    def transaction_type(self) -> TransactionType:
        return self._transaction_type

    @property
    def commission(self) -> Decimal:
        return self._commission

    @property
    def status(self) -> TransactionStatus:
        return self._status

    @property
    def reason(self) -> str | None:
        return self._reason

    @property
    def sender(self) -> BankAccount:
        return self._sender

    @property
    def acceptor(self) -> BankAccount:
        return self._acceptor

    @property
    def errors(self) -> tuple[tuple[datetime, str], ...]:
        return tuple(self._errors)

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def __init__(
        self,
        *,
        amount: Decimal,
        transaction_type: TransactionType,
        acceptor: BankAccount,
        sender: BankAccount
    ) -> None:
        if amount <= Decimal("0"):
            raise ValueError("Transaction amount must be positive")

        now = datetime.now(timezone.utc)

        self._id = uuid4()
        self._amount = amount
        self._currency_from = sender.currency
        self._currency_to = acceptor.currency
        self._commission = Decimal("0")
        self._sender = sender
        self._acceptor = acceptor
        self._transaction_type = transaction_type
        self._status = TransactionStatus.ACTIVE
        self._reason: str | None = None
        self._errors: list[tuple[datetime, str]] = []
        self._updated_at = now
        self._created_at = now

    def fail(self, reason: str) -> None:
        if self._status not in (
            TransactionStatus.ACTIVE,
            TransactionStatus.PROCESSING,
        ):
            raise InvalidOperationError(
                f"Cannot fail transaction with status {self._status}"
            )

        reason = reason.strip()

        if not reason:
            raise ValueError("Failure reason cannot be empty")

        self._status = TransactionStatus.FAILED
        self._reason = reason
        self._updated_at = datetime.now(timezone.utc)

    def start_processing(self) -> None:
        if self._status != TransactionStatus.ACTIVE:
            raise InvalidOperationError(
                f"Cannot process transaction with status {self._status}"
            )

        self._status = TransactionStatus.PROCESSING
        self._updated_at = datetime.now(timezone.utc)

    def cancel(self, reason: str) -> None:
        if self._status != TransactionStatus.ACTIVE:
            raise InvalidOperationError(
                f"Cannot cancel transaction with status {self._status}"
            )

        reason = reason.strip()

        if not reason:
            raise ValueError("Failure reason cannot be empty")

        self._status = TransactionStatus.CANCELLED
        self._reason = reason
        self._updated_at = datetime.now(timezone.utc)

    def complete(self) -> None:
        if self._status != TransactionStatus.PROCESSING:
            raise InvalidOperationError(
                f"Cannot complete transaction with status {self._status}"
            )

        self._status = TransactionStatus.COMPLETED
        self._updated_at = datetime.now(timezone.utc)

    def set_commission(self, commission: Decimal) -> None:
        if commission < Decimal("0"):
            raise ValueError("Commission cannot be negative")

        self._commission = commission

    def add_error(self, error: str) -> None:
        now = datetime.now(timezone.utc)

        self._errors.append((now, error))
        self._updated_at = now


class TransactionQueue:
    def __init__(self) -> None:
        self._scheduled_queue: list[
            tuple[datetime, int, int, Transaction]
        ] = []

        self._ready_queue: list[
            tuple[int, int, Transaction]
        ] = []

        # Lazy deletion ускоряет cancel(), но отменённые элементы
        # остаются в heap до их извлечения и временно занимают память.
        self._transactions: dict[UUID, Transaction] = {}

        self._counter = count()

    def put(
        self,
        *,
        transaction: Transaction,
        priority: TransactionPriority = TransactionPriority.NORMAL,
        execute_at: datetime | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)

        if execute_at is None:
            execute_at = now

        if transaction.id in self._transactions:
            raise ValueError("Transaction is already in queue")

        self._transactions[transaction.id] = transaction

        order = next(self._counter)

        if execute_at <= now:
            heapq.heappush(
                self._ready_queue,
                (
                    -priority.value,
                    order,
                    transaction,
                ),
            )

            return

        heapq.heappush(
            self._scheduled_queue,
            (
                execute_at,
                order,
                -priority.value,
                transaction,
            ),
        )

    def get(self) -> Transaction | None:
        self._move_ready_transactions()

        while self._ready_queue:
            _, _, transaction = heapq.heappop(
                self._ready_queue
            )

            if transaction.id not in self._transactions:
                continue

            self._transactions.pop(transaction.id)

            return transaction

        return None

    def cancel(self, transaction_id: UUID, reason: str) -> bool:
        transaction = self._transactions.pop(
            transaction_id,
            None,
        )

        if transaction is None:
            return False

        transaction.cancel(reason)

        return True

    def is_empty(self) -> bool:
        return not self._transactions

    def _move_ready_transactions(self) -> None:
        now = datetime.now(timezone.utc)

        while self._scheduled_queue:
            execute_at, order, priority, transaction = (
                self._scheduled_queue[0]
            )

            if execute_at > now:
                break

            heapq.heappop(self._scheduled_queue)

            if transaction.id not in self._transactions:
                continue

            heapq.heappush(
                self._ready_queue,
                (
                    priority,
                    order,
                    transaction,
                ),
            )


class CommissionCalculator:
    EXTERNAL_COMMISSION = Decimal("0.01")

    def calculate(
        self,
        transaction: Transaction,
    ) -> Decimal:
        if transaction.transaction_type == TransactionType.INTERNAL:
            return Decimal("0")

        return (
            transaction.amount
            * self.EXTERNAL_COMMISSION
        )


class CurrencyConverter:
    RUB_RATES: ClassVar[dict[AccountCurrency, Decimal]] = {
        AccountCurrency.RUB: Decimal("1.0"),
        AccountCurrency.USD: Decimal("82.1665"),
        AccountCurrency.EUR: Decimal("94.8366"),
        AccountCurrency.KZT: Decimal("0.175765"),
        AccountCurrency.CNY: Decimal("12.1655"),
    }

    def convert(
        self,
        *,
        amount: Decimal,
        from_currency: AccountCurrency,
        to_currency: AccountCurrency,
    ) -> Decimal:
        if from_currency == to_currency:
            return amount

        rate = self.get_rate(
            from_currency,
            to_currency,
        )

        return amount * rate

    def get_rate(
        self,
        from_currency: AccountCurrency,
        to_currency: AccountCurrency,
    ) -> Decimal:
        if from_currency == to_currency:
            return Decimal("1.0")

        from_rate = self.RUB_RATES.get(from_currency)
        to_rate = self.RUB_RATES.get(to_currency)

        if from_rate is None:
            raise ValueError(
                f"Unsupported currency: {from_currency}"
            )

        if to_rate is None:
            raise ValueError(
                f"Unsupported currency: {to_currency}"
            )

        return from_rate / to_rate


class TransactionProcessor:
    MAX_RETRIES = 3

    def __init__(
        self,
        commission_calculator: CommissionCalculator,
        currency_converter: CurrencyConverter,
    ) -> None:
        self._commission_calculator = commission_calculator
        self._currency_converter = currency_converter

    def process(self, transaction: Transaction) -> None:
        transaction.start_processing()

        for attempt in range(self.MAX_RETRIES):
            try:
                # Нужна транзакция БД для атомарного withdraw/deposit и безопасного retry
                self._process(transaction)
            except (
                InsufficientFundsError,
                AccountFrozenError,
                InvalidOperationError
            ) as error:
                transaction.add_error(str(error))
                transaction.fail(str(error))
                return

            except RetryableTransactionError as error:
                transaction.add_error(str(error))

                if attempt == self.MAX_RETRIES - 1:
                    transaction.fail(str(error))
                    return
            else:
                transaction.complete()
                return

    def _process(self, transaction: Transaction) -> None:
        sender = transaction.sender
        acceptor = transaction.acceptor

        commission = self._commission_calculator.calculate(
            transaction
        )

        transaction.set_commission(commission)

        total_amount = (
            transaction.amount
            + commission
        )

        converted_amount = self._currency_converter.convert(
            amount=transaction.amount,
            from_currency=transaction.currency_from,
            to_currency=transaction.currency_to,
        )

        sender.withdraw(total_amount)
        acceptor.deposit(converted_amount)
