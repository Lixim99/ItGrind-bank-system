import importlib
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from src.enums import (
    AccountCurrency,
    AuditLevel,
    RiskLevel,
    TransactionStatus,
    TransactionType,
)
from src.models import BankAccount
from src.utils import BANK_TIMEZONE


@pytest.fixture
def audit_api():
    try:
        return importlib.import_module("src.audit")
    except ImportError as error:
        pytest.skip(f"Covered by the transaction import test: {error}")


@pytest.fixture
def transaction_api():
    try:
        return importlib.import_module("src.transaction")
    except ImportError as error:
        pytest.skip(f"Covered by the transaction import test: {error}")


def test_audit_log_persists_and_filters_records(audit_api, tmp_path):
    transaction_id = uuid4()
    client_id = uuid4()
    audit_log = audit_api.AuditLog(tmp_path / "audit.jsonl")

    audit_log.log(
        level=AuditLevel.WARNING,
        message="Suspicious transfer",
        transaction_id=transaction_id,
        client_id=client_id,
        metadata={"score": 3},
    )
    audit_log.log(level=AuditLevel.INFO, message="Transfer completed")

    assert isinstance(audit_log.records, tuple)
    assert len(audit_log.filter(level=AuditLevel.WARNING)) == 1
    assert len(audit_log.filter(transaction_id=transaction_id)) == 1
    assert len(audit_log.filter(client_id=client_id)) == 1
    assert len((tmp_path / "audit.jsonl").read_text().splitlines()) == 2
    assert audit_log.records[0].timestamp.tzinfo == BANK_TIMEZONE


def test_audit_reporter_builds_required_reports(audit_api, tmp_path):
    client_id = uuid4()
    audit_log = audit_api.AuditLog(tmp_path / "audit.jsonl")
    audit_log.log(
        level=AuditLevel.CRITICAL,
        message="Blocked",
        client_id=client_id,
    )
    audit_log.log(level=AuditLevel.INFO, message="Completed")
    reporter = audit_api.AuditReporter(audit_log)

    assert len(reporter.suspicious_operations()) == 1
    assert reporter.error_statistics() == {"Blocked": 1}
    assert len(reporter.client_risk_profile(client_id)) == 1


def test_risk_analyzer_detects_large_night_transfer(
    audit_api,
    transaction_api,
    client_factory,
):
    sender = BankAccount(
        client=client_factory(1),
        currency=AccountCurrency.RUB,
    )
    receiver = BankAccount(
        client=client_factory(2),
        currency=AccountCurrency.RUB,
    )
    transaction = transaction_api.Transaction(
        amount=Decimal("100000"),
        transaction_type=TransactionType.INTERNAL,
        sender=sender,
        acceptor=receiver,
    )
    transaction._created_at = datetime(
        2025,
        12,
        31,
        22,
        tzinfo=timezone.utc,
    )

    assessment = audit_api.RiskAnalyzer().analyze(transaction)

    assert assessment.level is RiskLevel.HIGH
    assert "Large transaction" in assessment.reasons
    assert "Transfer to new account" in assessment.reasons
    assert "Night operation" in assessment.reasons


def test_high_risk_transaction_is_blocked_and_audited(
    audit_api,
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
    sender.deposit(Decimal("200000"))
    transaction = transaction_api.Transaction(
        amount=Decimal("100000"),
        transaction_type=TransactionType.INTERNAL,
        sender=sender,
        acceptor=receiver,
    )
    transaction._created_at = datetime(
        2025,
        12,
        31,
        22,
        tzinfo=timezone.utc,
    )
    audit_log = audit_api.AuditLog(tmp_path / "audit.jsonl")
    processor = transaction_api.TransactionProcessor(
        commission_calculator=transaction_api.CommissionCalculator(),
        currency_converter=transaction_api.CurrencyConverter(),
        risk_analyzer=audit_api.RiskAnalyzer(),
        audit_log=audit_log,
        operation_policy=allowed_operation_policy,
    )

    processor.process(transaction)

    assert transaction.status is TransactionStatus.FAILED
    assert sender.balance == Decimal("200000")
    assert receiver.balance == Decimal("0")
    assert audit_log.records[-1].level is AuditLevel.CRITICAL
    assert audit_log.records[-1].client_id == sender.client.id
