import csv
import json
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from .audit import AuditLog
from .bank import Bank
from .enums import AccountCurrency, AuditLevel, TransactionStatus
from .models import BankAccount, Client
from .transaction import Transaction

ReportData = dict[str, Any]
MAX_TIME_LABELS = 8


def _select_label_positions(points_count: int) -> list[int]:
    """Выбрать не более восьми равномерных подписей оси."""
    if points_count <= MAX_TIME_LABELS:
        return list(range(points_count))

    last_position = points_count - 1
    return sorted(
        {
            round(index * last_position / (MAX_TIME_LABELS - 1))
            for index in range(MAX_TIME_LABELS)
        }
    )


def _format_chart_time(timestamp: datetime) -> str:
    """Показать дату и московское время с миллисекундами."""
    return timestamp.strftime("%d.%m.%Y\n%H:%M:%S.%f")[:-3]


class ReportBuilder:
    def __init__(
            self,
            *,
            bank: Bank,
            audit_log: AuditLog,
            transactions: list[Transaction],
    ):
        self._bank = bank
        self._audit_log = audit_log
        self._transactions = transactions

    def build_transactions_report(
        self,
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": str(transaction.id),
                "amount": str(transaction.amount),
                "currency_from": transaction.currency_from.value,
                "currency_to": transaction.currency_to.value,
                "commission": str(transaction.commission),
                "status": transaction.status.value,
                "sender": str(transaction.sender.id),
                "acceptor": str(transaction.acceptor.id),
                "created_at": transaction.created_at.isoformat(),
                "reason": transaction.reason or "",
            }
            for transaction in self._transactions
        ]

    def build_client_report(self, client: Client) -> ReportData:
        accounts = client.accounts

        total_balances: dict[str, Decimal] = {}

        for account in accounts:
            currency = account.currency.value
            total_balances[currency] = (
                total_balances.get(currency, Decimal(0))
                + account.balance
            )

        return {
            "client_id": str(client.id),
            "name": (
                f"{client.first_name} "
                f"{client.last_name}"
            ),
            "accounts_count": len(accounts),
            "total_balances": {
                currency: str(balance)
                for currency, balance in total_balances.items()
            },
            "accounts": [
                {
                    "id": str(account.id),
                    "currency": account.currency.value,
                    "balance": str(account.balance),
                    "status": account.status.value,
                }
                for account in accounts
            ],
        }

    def build_bank_report(self):
        clients = list(self._bank.clients.values())
        accounts = list(self._bank.accounts.values())

        return {
            "clients_count": len(clients),
            "accounts_count": len(accounts),
            "total_balances": {
                currency.value: str(
                    self._bank.get_total_balance(currency)
                )
                for currency in AccountCurrency
            },
            "clients": [
                {
                    "id": str(client.id),
                    "name": (
                        f"{client.first_name} "
                        f"{client.last_name}"
                    ),
                    "accounts_count": len(client.accounts),
                }
                for client in clients
            ],
        }

    def build_risk_report(self):
        suspicious = [
            record
            for record in self._audit_log.records
            if record.level in (
                AuditLevel.WARNING,
                AuditLevel.CRITICAL,
            )
        ]

        return {
            "suspicious_operations_count": len(
                suspicious
            ),
            "operations": [
                {
                    "timestamp": (
                        record.timestamp.isoformat()
                    ),
                    "level": record.level.value,
                    "message": record.message,
                    "transaction_id": (
                        str(record.transaction_id)
                        if record.transaction_id
                        else None
                    ),
                }
                for record in suspicious
            ],
        }

    def export_to_json(
        self,
        report: ReportData,
        file_path: str | Path,
    ) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                report,
                file,
                ensure_ascii=False,
                indent=4,
            )

    def export_to_csv(
        self,
        rows: list[dict[str, Any]],
        file_path: str | Path,
    ) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if not rows:
            path.write_text("", encoding="utf-8")
            return

        with path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=rows[0].keys(),
            )

            writer.writeheader()
            writer.writerows(rows)

    def to_text(
        self,
        report: ReportData,
    ) -> str:
        lines: list[str] = []

        for key, value in report.items():
            lines.append(
                f"{key}: {value}"
            )

        return "\n".join(lines)

    def save_charts(
        self,
        directory: str | Path,
        currency: AccountCurrency = AccountCurrency.RUB,
    ) -> None:
        directory = Path(directory)

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._save_clients_balance_chart(
            clients=list(self._bank.clients.values()),
            file_path=directory / "client_balances.png",
            currency=currency
        )

        self._save_transaction_statuses(
            file_path=directory / "transaction_statuses.png",
        )

    def _save_transaction_statuses(
        self,
        file_path: str | Path,
    ) -> None:
        completed = sum(
            transaction.status == TransactionStatus.COMPLETED
            for transaction in self._transactions
        )

        failed = sum(
            transaction.status == TransactionStatus.FAILED
            for transaction in self._transactions
        )

        cancelled = sum(
            transaction.status == TransactionStatus.CANCELLED
            for transaction in self._transactions
        )

        self._save_transaction_status_chart(
            completed=completed,
            failed=failed,
            cancelled=cancelled,
            file_path=file_path,
        )

    def _save_transaction_status_chart(
        self,
        *,
        completed: int,
        failed: int,
        cancelled: int,
        file_path: str | Path,
    ) -> None:
        labels = [
            "Completed",
            "Failed",
            "Cancelled",
        ]

        values = [
            completed,
            failed,
            cancelled,
        ]

        plt.figure()

        if any(values):
            plt.pie(
                values,
                labels=labels,
                autopct="%1.1f%%",
            )
        else:
            plt.text(
                0.5,
                0.5,
                "No transactions",
                horizontalalignment="center",
                verticalalignment="center",
            )
            plt.axis("off")

        plt.title("Transaction statuses")

        plt.savefig(file_path)
        plt.close()

    def _save_clients_balance_chart(
        self,
        clients: list[Client],
        file_path: str | Path,
        currency: AccountCurrency
    ) -> None:
        names = [
            client.first_name
            for client in clients
        ]

        balances = [
            float(
                self._bank.get_total_balance(
                    client=client,
                    currency=currency
                )
            )
            for client in clients
        ]

        plt.figure()

        plt.bar(
            names,
            balances,
        )

        plt.title("Client balances")
        plt.xlabel("Client")
        plt.ylabel("Balance")

        plt.savefig(file_path)
        plt.close()

    def save_account_balance_chart(
        self,
        *,
        account: BankAccount,
        file_path: str | Path,
    ) -> None:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        self._save_balance_history_chart(
            account=account,
            file_path=file_path,
        )

    def _save_balance_history_chart(
        self,
        *,
        account: BankAccount,
        file_path: str | Path,
    ) -> None:
        history = account.balance_history

        if not history:
            return

        timestamps: Sequence[datetime] = [
            timestamp
            for timestamp, _ in history
        ]

        balances = [
            float(balance)
            for _, balance in history
        ]

        plt.figure(figsize=(10, 6))

        operation_numbers = range(1, len(history) + 1)

        plt.plot(
            operation_numbers,
            balances,
            marker="o",
        )

        plt.title(
            f"История баланса: ***{account.account_number[-4:]}"
        )
        plt.xlabel("Время операции (Москва)")
        plt.ylabel(
            f"Баланс ({account.currency.value})"
        )

        label_positions = _select_label_positions(len(history))
        plt.xticks(
            ticks=[position + 1 for position in label_positions],
            labels=[
                _format_chart_time(timestamps[position])
                for position in label_positions
            ],
            rotation=35,
            ha="right",
        )
        plt.tight_layout()

        plt.savefig(file_path)
        plt.close()
