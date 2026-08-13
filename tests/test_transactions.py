from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.audit import AuditLog, RiskAnalyzer
from src.enums import (
    AccountCurrency,
    AccountStatus,
    AuditLevel,
    RiskLevel,
    TransactionPriority,
    TransactionStatus,
    TransactionType,
)
from src.exceptions import InvalidOperationError
from src.models import BankAccount, PremiumAccount, SavingsAccount
from src.transaction import (
    CommissionCalculator,
    CurrencyConverter,
    RetryableTransactionError,
    Transaction,
    TransactionProcessor,
    TransactionQueue,
)
from src.utils import BANK_TIMEZONE


@pytest.fixture
def accounts(client_factory):
    sender = BankAccount(
        client=client_factory(1),
        currency=AccountCurrency.RUB,
    )
    receiver = BankAccount(
        client=client_factory(2),
        currency=AccountCurrency.USD,
    )
    sender.deposit(Decimal("10000"))
    return sender, receiver


def make_transaction(sender, receiver, **overrides):
    values = {
        "amount": Decimal("100"),
        "transaction_type": TransactionType.INTERNAL,
        "sender": sender,
        "acceptor": receiver,
    }
    values.update(overrides)
    return Transaction(**values)


def make_low_risk_processor(
    operation_policy,
    *,
    converter=None,
    audit_log=None,
):
    risk_analyzer = SimpleNamespace(
        analyze=lambda _transaction: SimpleNamespace(
            level=RiskLevel.LOW,
            reasons=(),
        )
    )
    return TransactionProcessor(
        commission_calculator=CommissionCalculator(),
        currency_converter=converter or CurrencyConverter(),
        risk_analyzer=risk_analyzer,
        audit_log=audit_log or SimpleNamespace(log=lambda **_values: None),
        operation_policy=operation_policy,
    )


def test_day4_transaction_contains_required_fields_and_timestamps(accounts):
    transaction = make_transaction(*accounts)

    assert transaction.id is not None
    assert transaction.amount == Decimal("100")
    assert transaction.currency_from is AccountCurrency.RUB
    assert transaction.currency_to is AccountCurrency.USD
    assert transaction.commission == Decimal("0")
    assert transaction.sender is accounts[0]
    assert transaction.acceptor is accounts[1]
    assert transaction.status is TransactionStatus.ACTIVE
    assert transaction.reason is None
    assert transaction.created_at.tzinfo == BANK_TIMEZONE
    assert transaction.updated_at == transaction.created_at


@pytest.mark.parametrize(
    "amount",
    [Decimal("0"), Decimal("-1"), Decimal("NaN"), 100],
)
def test_day4_transaction_validates_amount(accounts, amount):
    with pytest.raises(ValueError):
        make_transaction(*accounts, amount=amount)


def test_day4_transaction_state_machine_and_self_transfer(accounts):
    transaction = make_transaction(*accounts)
    transaction.start_processing()
    transaction.complete()

    assert transaction.status is TransactionStatus.COMPLETED

    with pytest.raises(InvalidOperationError):
        transaction.cancel("Too late")

    with pytest.raises(InvalidOperationError, match="yourself"):
        make_transaction(accounts[0], accounts[0])


def test_day4_queue_handles_priority_scheduling_and_cancellation(accounts):
    current_time = datetime(2026, 1, 1, 12, tzinfo=BANK_TIMEZONE)
    clock = SimpleNamespace(now=current_time)
    queue = TransactionQueue(clock=lambda: clock.now)
    low = make_transaction(*accounts)
    critical = make_transaction(*accounts)
    delayed = make_transaction(*accounts)

    queue.put(transaction=low, priority=TransactionPriority.LOW)
    queue.put(transaction=critical, priority=TransactionPriority.CRITICAL)
    queue.put(transaction=delayed, execute_at=current_time + timedelta(hours=1))

    assert queue.get() is critical
    assert queue.get() is low
    assert queue.get() is None
    assert queue.cancel(delayed.id, "Cancelled by client")
    assert delayed.status is TransactionStatus.CANCELLED
    assert queue.is_empty()


def test_day4_scheduled_transaction_becomes_ready(accounts):
    clock = SimpleNamespace(
        now=datetime(2026, 1, 1, 12, tzinfo=BANK_TIMEZONE)
    )
    queue = TransactionQueue(clock=lambda: clock.now)
    delayed = make_transaction(*accounts)
    queue.put(transaction=delayed, execute_at=clock.now + timedelta(minutes=5))

    assert queue.get() is None
    clock.now += timedelta(minutes=5)
    assert queue.get() is delayed


def test_day4_external_commission_and_currency_conversion(accounts):
    transaction = make_transaction(
        *accounts,
        transaction_type=TransactionType.EXTERNAL,
    )
    converter = CurrencyConverter()

    assert CommissionCalculator().calculate(transaction) == Decimal("1.00")
    assert converter.convert(
        amount=Decimal("100"),
        from_currency=AccountCurrency.USD,
        to_currency=AccountCurrency.RUB,
    ) == Decimal("8216.6500")


@pytest.mark.parametrize(
    ("account_class", "transaction_type", "expected_balance"),
    [
        (BankAccount, TransactionType.INTERNAL, Decimal("900")),
        (BankAccount, TransactionType.EXTERNAL, Decimal("899")),
        (SavingsAccount, TransactionType.INTERNAL, Decimal("900")),
        (SavingsAccount, TransactionType.EXTERNAL, Decimal("899")),
        (PremiumAccount, TransactionType.INTERNAL, Decimal("900")),
        (PremiumAccount, TransactionType.EXTERNAL, Decimal("899")),
    ],
)
def test_day4_processor_charges_transfer_commission_exactly_once(
    client_factory,
    allowed_operation_policy,
    account_class,
    transaction_type,
    expected_balance,
):
    sender = account_class(
        client=client_factory(1),
        currency=AccountCurrency.RUB,
    )
    receiver = BankAccount(
        client=client_factory(2),
        currency=AccountCurrency.RUB,
    )
    sender.deposit(Decimal("1000"))
    transaction = make_transaction(
        sender,
        receiver,
        transaction_type=transaction_type,
    )

    make_low_risk_processor(allowed_operation_policy).process(transaction)

    assert transaction.status is TransactionStatus.COMPLETED
    assert sender.balance == expected_balance
    assert receiver.balance == Decimal("100")


def test_day4_premium_transfer_can_use_overdraft(
    client_factory,
    allowed_operation_policy,
):
    sender = PremiumAccount(
        client=client_factory(1),
        currency=AccountCurrency.RUB,
    )
    receiver = BankAccount(
        client=client_factory(2),
        currency=AccountCurrency.RUB,
    )
    transaction = make_transaction(sender, receiver)

    make_low_risk_processor(allowed_operation_policy).process(transaction)

    assert transaction.status is TransactionStatus.COMPLETED
    assert sender.balance == Decimal("-100")


def test_day4_failed_credit_rolls_back_balance_and_history(
    client_factory,
    allowed_operation_policy,
    tmp_path,
):
    sender = BankAccount(
        client=client_factory(1),
        currency=AccountCurrency.RUB,
    )
    receiver = BankAccount(
        client=client_factory(2),
        currency=AccountCurrency.RUB,
    )
    sender.deposit(Decimal("1000"))
    receiver.change_account_status(AccountStatus.FROZEN)
    history_before = sender.balance_history
    transaction = make_transaction(sender, receiver)
    audit_log = AuditLog(tmp_path / "audit.jsonl")
    processor = TransactionProcessor(
        commission_calculator=CommissionCalculator(),
        currency_converter=CurrencyConverter(),
        risk_analyzer=RiskAnalyzer(),
        audit_log=audit_log,
        operation_policy=allowed_operation_policy,
    )

    processor.process(transaction)

    assert transaction.status is TransactionStatus.FAILED
    assert sender.balance == Decimal("1000")
    assert receiver.balance == Decimal("0")
    assert sender.balance_history == history_before
    assert audit_log.records[-1].level is AuditLevel.CRITICAL


def test_day4_night_operation_is_blocked_before_balance_change(
    accounts,
    night_operation_policy,
    tmp_path,
):
    transaction = make_transaction(*accounts)
    audit_log = AuditLog(tmp_path / "audit.jsonl")
    processor = TransactionProcessor(
        commission_calculator=CommissionCalculator(),
        currency_converter=CurrencyConverter(),
        risk_analyzer=RiskAnalyzer(),
        audit_log=audit_log,
        operation_policy=night_operation_policy,
    )

    processor.process(transaction)

    assert transaction.status is TransactionStatus.FAILED
    assert accounts[0].balance == Decimal("10000")
    assert accounts[1].balance == Decimal("0")


def test_day4_processor_retries_temporary_errors(
    accounts,
    allowed_operation_policy,
):
    class FlakyConverter(CurrencyConverter):
        def __init__(self):
            self.calls = 0

        def convert(self, **values):
            self.calls += 1

            if self.calls < 3:
                raise RetryableTransactionError("Temporary failure")

            return super().convert(**values)

    converter = FlakyConverter()
    transaction = make_transaction(*accounts)
    processor = make_low_risk_processor(
        allowed_operation_policy,
        converter=converter,
    )

    processor.process(transaction)

    assert converter.calls == TransactionProcessor.MAX_RETRIES
    assert len(transaction.errors) == 2
    assert transaction.status is TransactionStatus.COMPLETED


def test_day4_processor_records_final_retry_error(
    accounts,
    allowed_operation_policy,
    tmp_path,
):
    class UnavailableConverter:
        def __init__(self):
            self.calls = 0

        def convert(self, **_values):
            self.calls += 1
            raise RetryableTransactionError("Currency service unavailable")

    converter = UnavailableConverter()
    audit_log = AuditLog(tmp_path / "audit.jsonl")
    transaction = make_transaction(*accounts)
    processor = make_low_risk_processor(
        allowed_operation_policy,
        converter=converter,
        audit_log=audit_log,
    )

    processor.process(transaction)

    assert converter.calls == TransactionProcessor.MAX_RETRIES
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.reason == "Currency service unavailable"
    assert audit_log.records[-1].level is AuditLevel.CRITICAL
