from datetime import datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import uuid4

from src.audit import AuditLog, AuditReporter, RiskAnalyzer
from src.enums import (
    AccountCurrency,
    AuditLevel,
    RiskLevel,
    TransactionStatus,
    TransactionType,
)
from src.models import BankAccount
from src.transaction import (
    CommissionCalculator,
    CurrencyConverter,
    Transaction,
    TransactionProcessor,
)
from src.utils import BANK_TIMEZONE


def make_transaction(
    client_factory,
    *,
    amount="100",
    created_at=None,
    sender=None,
    receiver=None,
):
    sender = sender or BankAccount(
        client=client_factory(1),
        currency=AccountCurrency.RUB,
    )
    receiver = receiver or BankAccount(
        client=client_factory(2),
        currency=AccountCurrency.RUB,
    )
    return Transaction(
        amount=Decimal(amount),
        transaction_type=TransactionType.INTERNAL,
        sender=sender,
        acceptor=receiver,
        created_at=created_at,
    )


def test_day5_audit_persists_in_memory_and_file_and_filters(tmp_path):
    transaction_id = uuid4()
    client_id = uuid4()
    audit_log = AuditLog(tmp_path / "nested" / "audit.jsonl")
    metadata = {"score": 3}
    audit_log.log(
        level=AuditLevel.WARNING,
        message="Suspicious transfer",
        transaction_id=transaction_id,
        client_id=client_id,
        metadata=metadata,
    )
    metadata["score"] = 999
    audit_log.log(level=AuditLevel.INFO, message="Transfer completed")

    assert isinstance(audit_log.records, tuple)
    assert isinstance(audit_log.records[0].metadata, MappingProxyType)
    assert audit_log.records[0].metadata["score"] == 3
    assert len(audit_log.filter(level=AuditLevel.WARNING)) == 1
    assert len(audit_log.filter(transaction_id=transaction_id)) == 1
    assert len(audit_log.filter(client_id=client_id)) == 1
    assert len((tmp_path / "nested" / "audit.jsonl").read_text().splitlines()) == 2


def test_day5_audit_reporter_builds_all_required_reports(tmp_path):
    client_id = uuid4()
    audit_log = AuditLog(tmp_path / "audit.jsonl")
    audit_log.log(
        level=AuditLevel.CRITICAL,
        message="Blocked",
        client_id=client_id,
    )
    audit_log.log(level=AuditLevel.INFO, message="Completed")
    reporter = AuditReporter(audit_log)

    assert len(reporter.suspicious_operations()) == 1
    assert reporter.error_statistics() == {"Blocked": 1}
    assert len(reporter.client_risk_profile(client_id)) == 1


def test_day5_risk_detects_large_new_and_night_operation(client_factory):
    transaction = make_transaction(
        client_factory,
        amount="100000",
        created_at=datetime(2026, 1, 1, 1, tzinfo=BANK_TIMEZONE),
    )

    assessment = RiskAnalyzer().analyze(transaction)

    assert assessment.level is RiskLevel.HIGH
    assert assessment.score == 4
    assert assessment.reasons == (
        "Large transaction",
        "Transfer to new account",
        "Night operation",
    )


def test_day5_ordinary_operation_has_low_risk(client_factory):
    transaction = make_transaction(
        client_factory,
        created_at=datetime(2026, 1, 1, 12, tzinfo=BANK_TIMEZONE),
    )

    assessment = RiskAnalyzer().analyze(transaction)

    assert assessment.level is RiskLevel.LOW
    assert assessment.score == 1
    assert assessment.reasons == ("Transfer to new account",)


def test_day5_risk_detects_frequent_operations(client_factory):
    sender = BankAccount(
        client=client_factory(1),
        currency=AccountCurrency.RUB,
    )
    receiver = BankAccount(
        client=client_factory(2),
        currency=AccountCurrency.RUB,
    )
    analyzer = RiskAnalyzer()
    started_at = datetime(2026, 1, 1, 12, tzinfo=BANK_TIMEZONE)

    for index in range(analyzer.FREQUENT_OPERATIONS_LIMIT):
        analyzer.analyze(
            make_transaction(
                client_factory,
                sender=sender,
                receiver=receiver,
                created_at=started_at + timedelta(seconds=index),
            )
        )

    assessment = analyzer.analyze(
        make_transaction(
            client_factory,
            sender=sender,
            receiver=receiver,
            created_at=started_at + timedelta(seconds=30),
        )
    )

    assert "Frequent operations" in assessment.reasons
    assert assessment.level is RiskLevel.MEDIUM


def test_day5_high_risk_operation_is_blocked_and_audited(
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
    sender.deposit(Decimal("200000"))
    transaction = make_transaction(
        client_factory,
        sender=sender,
        receiver=receiver,
        amount="100000",
        created_at=datetime(2026, 1, 1, 1, tzinfo=BANK_TIMEZONE),
    )
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
    assert sender.balance == Decimal("200000")
    assert receiver.balance == Decimal("0")
    assert audit_log.records[-1].level is AuditLevel.CRITICAL
