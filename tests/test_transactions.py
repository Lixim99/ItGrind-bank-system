import importlib
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

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
from src.audit import AuditLog, RiskAnalyzer
from src.models import BankAccount, PremiumAccount, SavingsAccount
from src.utils import BANK_TIMEZONE, bank_now


def test_transaction_module_can_be_imported():
    result = subprocess.run(
        [sys.executable, "-c", "import src.transaction"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.fixture
def transaction_api():
    try:
        return importlib.import_module("src.transaction")
    except ImportError as error:
        pytest.skip(f"Covered by the transaction import test: {error}")


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


def make_transaction(api, sender, receiver, **overrides):
    values = {
        "amount": Decimal("100"),
        "transaction_type": TransactionType.INTERNAL,
        "sender": sender,
        "acceptor": receiver,
    }
    values.update(overrides)
    return api.Transaction(**values)


def make_low_risk_processor(
    api,
    operation_policy,
    *,
    currency_converter=None,
    audit_log=None,
):
    risk_analyzer = SimpleNamespace(
        analyze=lambda _transaction: SimpleNamespace(
            level=RiskLevel.LOW,
            reasons=(),
        )
    )

    return api.TransactionProcessor(
        commission_calculator=api.CommissionCalculator(),
        currency_converter=(
            currency_converter or api.CurrencyConverter()
        ),
        risk_analyzer=risk_analyzer,
        audit_log=(
            audit_log or SimpleNamespace(log=lambda **_values: None)
        ),
        operation_policy=operation_policy,
    )


def test_transaction_state_machine(transaction_api, accounts):
    transaction = make_transaction(transaction_api, *accounts)

    assert transaction.status is TransactionStatus.ACTIVE
    assert transaction.commission == Decimal("0")
    assert transaction.created_at.tzinfo == BANK_TIMEZONE

    transaction.start_processing()
    transaction.complete()

    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.updated_at >= transaction.created_at


def test_queue_respects_priority_and_supports_cancellation(
    transaction_api,
    accounts,
):
    queue = transaction_api.TransactionQueue()
    low = make_transaction(transaction_api, *accounts)
    critical = make_transaction(transaction_api, *accounts)
    cancelled = make_transaction(transaction_api, *accounts)

    queue.put(transaction=low, priority=TransactionPriority.LOW)
    queue.put(transaction=critical, priority=TransactionPriority.CRITICAL)
    queue.put(
        transaction=cancelled,
        execute_at=bank_now() + timedelta(hours=1),
    )

    assert queue.cancel(cancelled.id, "Cancelled by client")
    assert cancelled.status is TransactionStatus.CANCELLED
    assert queue.get() is critical
    assert queue.get() is low
    assert queue.is_empty()


def test_external_commission_and_currency_conversion(transaction_api, accounts):
    sender, receiver = accounts
    transaction = make_transaction(
        transaction_api,
        sender,
        receiver,
        transaction_type=TransactionType.EXTERNAL,
    )
    calculator = transaction_api.CommissionCalculator()
    converter = transaction_api.CurrencyConverter()

    assert calculator.calculate(transaction) == Decimal("1.00")
    assert converter.convert(
        amount=Decimal("100"),
        from_currency=AccountCurrency.RUB,
        to_currency=AccountCurrency.RUB,
    ) == Decimal("100")
    assert converter.convert(
        amount=Decimal("100"),
        from_currency=AccountCurrency.USD,
        to_currency=AccountCurrency.RUB,
    ) == Decimal("8216.6500")


def test_processor_completes_transfer(
    transaction_api,
    accounts,
    allowed_operation_policy,
):
    sender, receiver = accounts
    transaction = make_transaction(transaction_api, sender, receiver)
    risk_analyzer = SimpleNamespace(
        analyze=lambda _transaction: SimpleNamespace(
            level=RiskLevel.LOW,
            reasons=(),
        )
    )
    audit_log = SimpleNamespace(log=lambda **_values: None)
    processor = transaction_api.TransactionProcessor(
        commission_calculator=transaction_api.CommissionCalculator(),
        currency_converter=transaction_api.CurrencyConverter(),
        risk_analyzer=risk_analyzer,
        audit_log=audit_log,
        operation_policy=allowed_operation_policy,
    )

    processor.process(transaction)

    assert transaction.status is TransactionStatus.COMPLETED
    assert receiver.balance > Decimal("0")
    assert transaction.reason is None


def test_failed_credit_rolls_back_sender_balance(
    transaction_api,
    client_factory,
    tmp_path,
    allowed_operation_policy,
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

    transaction = transaction_api.Transaction(
        amount=Decimal("100"),
        transaction_type=TransactionType.INTERNAL,
        sender=sender,
        acceptor=receiver,
    )

    audit_log = AuditLog(tmp_path / "audit.jsonl")
    processor = transaction_api.TransactionProcessor(
        commission_calculator=transaction_api.CommissionCalculator(),
        currency_converter=transaction_api.CurrencyConverter(),
        risk_analyzer=RiskAnalyzer(),
        audit_log=audit_log,
        operation_policy=allowed_operation_policy,
    )

    processor.process(transaction)

    assert transaction.status is TransactionStatus.FAILED
    assert sender.balance == Decimal("1000")
    assert receiver.balance == Decimal("0")
    assert audit_log.records[-1].level is AuditLevel.CRITICAL
    assert audit_log.records[-1].client_id == sender.client.id


def test_night_operation_is_blocked_before_balances_change(
    transaction_api,
    client_factory,
    tmp_path,
    night_operation_policy,
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
    transaction = make_transaction(transaction_api, sender, receiver)
    audit_log = AuditLog(tmp_path / "audit.jsonl")
    processor = transaction_api.TransactionProcessor(
        commission_calculator=transaction_api.CommissionCalculator(),
        currency_converter=transaction_api.CurrencyConverter(),
        risk_analyzer=RiskAnalyzer(),
        audit_log=audit_log,
        operation_policy=night_operation_policy,
    )

    processor.process(transaction)

    assert transaction.status is TransactionStatus.FAILED
    assert sender.balance == Decimal("1000")
    assert receiver.balance == Decimal("0")
    assert audit_log.records[-1].level is AuditLevel.WARNING
    assert audit_log.records[-1].client_id == sender.client.id


@pytest.mark.parametrize(
    (
        "account_class",
        "transaction_type",
        "expected_commission",
        "expected_sender_balance",
    ),
    [
        (
            BankAccount,
            TransactionType.INTERNAL,
            Decimal("0"),
            Decimal("900"),
        ),
        (
            BankAccount,
            TransactionType.EXTERNAL,
            Decimal("1"),
            Decimal("899"),
        ),
        (
            SavingsAccount,
            TransactionType.INTERNAL,
            Decimal("0"),
            Decimal("900"),
        ),
        (
            SavingsAccount,
            TransactionType.EXTERNAL,
            Decimal("1"),
            Decimal("899"),
        ),
        (
            PremiumAccount,
            TransactionType.INTERNAL,
            Decimal("0"),
            Decimal("900"),
        ),
        (
            PremiumAccount,
            TransactionType.EXTERNAL,
            Decimal("1"),
            Decimal("899"),
        ),
    ],
)
def test_transfer_charges_commission_exactly_once(
    transaction_api,
    client_factory,
    allowed_operation_policy,
    account_class,
    transaction_type,
    expected_commission,
    expected_sender_balance,
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
        transaction_api,
        sender,
        receiver,
        transaction_type=transaction_type,
    )
    processor = make_low_risk_processor(
        transaction_api,
        allowed_operation_policy,
    )

    processor.process(transaction)

    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.commission == expected_commission
    assert sender.balance == expected_sender_balance
    assert receiver.balance == Decimal("100")


def test_savings_transfer_preserves_minimum_balance(
    transaction_api,
    client_factory,
    allowed_operation_policy,
):
    sender = SavingsAccount(
        client=client_factory(1),
        currency=AccountCurrency.RUB,
    )
    receiver = BankAccount(
        client=client_factory(2),
        currency=AccountCurrency.RUB,
    )
    sender.deposit(Decimal("150"))
    transaction = make_transaction(
        transaction_api,
        sender,
        receiver,
    )
    processor = make_low_risk_processor(
        transaction_api,
        allowed_operation_policy,
    )

    processor.process(transaction)

    assert transaction.status is TransactionStatus.FAILED
    assert "Balance cannot be below" in transaction.reason
    assert sender.balance == Decimal("150")
    assert receiver.balance == Decimal("0")


def test_premium_transfer_can_use_overdraft(
    transaction_api,
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
    transaction = make_transaction(
        transaction_api,
        sender,
        receiver,
    )
    processor = make_low_risk_processor(
        transaction_api,
        allowed_operation_policy,
    )

    processor.process(transaction)

    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.commission == Decimal("0")
    assert sender.balance == Decimal("-100")
    assert receiver.balance == Decimal("100")


def test_processor_retries_temporary_error_and_then_completes(
    transaction_api,
    accounts,
    allowed_operation_policy,
):
    class FlakyCurrencyConverter(transaction_api.CurrencyConverter):
        def __init__(self) -> None:
            self.calls = 0

        def convert(self, **values):
            self.calls += 1

            if self.calls < 3:
                raise transaction_api.RetryableTransactionError(
                    "Temporary currency service failure"
                )

            return super().convert(**values)

    sender, receiver = accounts
    converter = FlakyCurrencyConverter()
    transaction = make_transaction(
        transaction_api,
        sender,
        receiver,
    )
    processor = make_low_risk_processor(
        transaction_api,
        allowed_operation_policy,
        currency_converter=converter,
    )

    processor.process(transaction)

    assert converter.calls == transaction_api.TransactionProcessor.MAX_RETRIES
    assert len(transaction.errors) == 2
    assert transaction.status is TransactionStatus.COMPLETED
    assert sender.balance == Decimal("9900")
    assert receiver.balance == transaction_api.CurrencyConverter().convert(
        amount=Decimal("100"),
        from_currency=sender.currency,
        to_currency=receiver.currency,
    )


def test_processor_fails_after_retry_limit(
    transaction_api,
    accounts,
    allowed_operation_policy,
):
    class UnavailableCurrencyConverter:
        def __init__(self) -> None:
            self.calls = 0

        def convert(self, **_values):
            self.calls += 1
            raise transaction_api.RetryableTransactionError(
                "Currency service is unavailable"
            )

    sender, receiver = accounts
    converter = UnavailableCurrencyConverter()
    transaction = make_transaction(
        transaction_api,
        sender,
        receiver,
    )
    processor = make_low_risk_processor(
        transaction_api,
        allowed_operation_policy,
        currency_converter=converter,
    )

    processor.process(transaction)

    assert converter.calls == transaction_api.TransactionProcessor.MAX_RETRIES
    assert (
        len(transaction.errors)
        == transaction_api.TransactionProcessor.MAX_RETRIES
    )
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.reason == "Currency service is unavailable"
    assert sender.balance == Decimal("10000")
    assert receiver.balance == Decimal("0")


def test_transaction_rejects_self_transfer(
    transaction_api,
    client_factory,
):
    account = BankAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )

    with pytest.raises(
        InvalidOperationError,
        match="can't send money yourself",
    ):
        make_transaction(
            transaction_api,
            account,
            account,
        )
