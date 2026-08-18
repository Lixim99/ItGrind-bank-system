from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping
from uuid import UUID

from .enums import AccountCurrency, AuditLevel, RiskLevel
from .exchange_rates import RUB_RATES
from .utils import bank_now, to_bank_time

if TYPE_CHECKING:
    from .transaction import Transaction


@dataclass(frozen=True)
class AuditRecord:
    timestamp: datetime
    level: AuditLevel
    message: str

    transaction_id: UUID | None = None
    client_id: UUID | None = None

    metadata: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )


class AuditLog:
    def __init__(self, file_path: str | Path):
        self._records: list[AuditRecord] = []
        self._file_path = Path(file_path)
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)

    def log(
        self,
        *,
        level: AuditLevel,
        message: str,
        transaction_id: UUID | None = None,
        client_id: UUID | None = None,
        metadata: dict[str, object] | None = None
    ) -> None:
        record = AuditRecord(
            timestamp=bank_now(),
            level=level,
            message=message,
            transaction_id=transaction_id,
            client_id=client_id,
            metadata=MappingProxyType(dict(metadata or {}))
        )

        self._records.append(record)
        self._save_to_file(record)

    def _save_to_file(self, record: AuditRecord) -> None:
        data = {
            "timestamp": record.timestamp,
            "level": record.level,
            "message": record.message,
            "transaction_id": record.transaction_id,
            "client_id": record.client_id,
            "metadata": dict(record.metadata),
        }

        with self._file_path.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )

    def filter(
        self,
        *,
        level: AuditLevel | None = None,
        transaction_id: UUID | None = None,
        client_id: UUID | None = None,
    ) -> tuple[AuditRecord, ...]:
        records = self._records

        if level is not None:
            records = [
                record
                for record in records
                if record.level == level
            ]

        if transaction_id is not None:
            records = [
                record
                for record in records
                if record.transaction_id == transaction_id
            ]

        if client_id is not None:
            records = [
                record
                for record in records
                if record.client_id == client_id
            ]

        return tuple(records)


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    score: int
    reasons: tuple[str, ...]


class RiskAnalyzer:
    BASE_CURRENCY = AccountCurrency.RUB
    LARGE_AMOUNT = Decimal("100000.0")

    FREQUENT_OPERATIONS_LIMIT = 5
    FREQUENT_OPERATIONS_WINDOW = timedelta(minutes=1)

    def __init__(self) -> None:
        self._history: list[Transaction] = []

    def analyze(self, transaction: Transaction) -> RiskAssessment:
        score: int = 0
        reasons: list[str] = []

        if self._is_large_amount(transaction):
            score += 2
            reasons.append("Large transaction")

        if self._has_frequent_operations(transaction):
            score += 2
            reasons.append("Frequent operations")

        if self._is_new_acceptor(transaction):
            score += 1
            reasons.append("Transfer to new account")

        if self._is_night_operation(transaction):
            score += 1
            reasons.append("Night operation")

        level = self._calculate_level(score)
        self._history.append(transaction)

        return RiskAssessment(
            level=level,
            score=score,
            reasons=tuple(reasons)
        )

    def _is_large_amount(self, transaction: Transaction) -> bool:
        amount_in_base_currency = (
            transaction.amount * RUB_RATES[transaction.currency_from]
        )

        return amount_in_base_currency >= self.LARGE_AMOUNT

    def _has_frequent_operations(self, transaction: Transaction) -> bool:
        window_start = transaction.created_at - self.FREQUENT_OPERATIONS_WINDOW

        operations_count = sum(
            1
            for item in self._history
            if (
                item.sender.id == transaction.sender.id
                and item.created_at >= window_start
                and item.created_at <= transaction.created_at
            )
        )

        return operations_count >= self.FREQUENT_OPERATIONS_LIMIT

    def _is_new_acceptor(self, transaction: Transaction) -> bool:
        return not any(
            item.sender.id == transaction.sender.id
            and item.acceptor.id == transaction.acceptor.id
            for item in self._history
        )

    def _is_night_operation(self, transaction: Transaction) -> bool:
        hour = to_bank_time(transaction.created_at).hour

        return 0 <= hour < 5

    def _calculate_level(self, score: int) -> RiskLevel:
        if score >= 4:
            return RiskLevel.HIGH

        if score >= 2:
            return RiskLevel.MEDIUM

        return RiskLevel.LOW


class AuditReporter:
    def __init__(self, audit_log: AuditLog) -> None:
        self._audit_log = audit_log

    def suspicious_operations(self) -> tuple[AuditRecord, ...]:
        return tuple(
            record
            for record in self._audit_log.records
            if record.level in (
                AuditLevel.WARNING,
                AuditLevel.CRITICAL
            )
        )

    def error_statistics(self) -> dict[str, int]:
        statistics: dict[str, int] = {}

        for record in self._audit_log.records:
            if record.level is not AuditLevel.CRITICAL:
                continue

            statistics[record.message] = (
                statistics.get(record.message, 0) + 1
            )

        return statistics

    def client_risk_profile(
        self,
        client_id: UUID,
    ) -> tuple[AuditRecord, ...]:
        return self._audit_log.filter(
            client_id=client_id
        )
