import csv
import json
from decimal import Decimal

from src.audit import AuditLog
from src.bank import Bank
from src.demo import run_demo
from src.enums import (
    AccountCurrency,
    AuditLevel,
    TransactionStatus,
    TransactionType,
)
from src.models import BankAccount
from src.report import (
    MAX_TIME_LABELS,
    ReportBuilder,
    _format_chart_time,
    _select_label_positions,
)
from src.transaction import Transaction


def make_report_builder(client_factory, tmp_path):
    bank = Bank()
    client = bank.add_client(client_factory())
    rub = bank.open_account(
        client=client,
        account_class=BankAccount,
        currency=AccountCurrency.RUB,
    )
    usd = bank.open_account(
        client=client,
        account_class=BankAccount,
        currency=AccountCurrency.USD,
    )
    receiver = bank.add_client(client_factory(2))
    receiver_account = bank.open_account(
        client=receiver,
        account_class=BankAccount,
        currency=AccountCurrency.RUB,
    )
    rub.deposit(Decimal("150"))
    usd.deposit(Decimal("25"))
    transaction = Transaction(
        amount=Decimal("10"),
        transaction_type=TransactionType.INTERNAL,
        sender=rub,
        acceptor=receiver_account,
    )
    audit_log = AuditLog(tmp_path / "audit.jsonl")
    audit_log.log(
        level=AuditLevel.WARNING,
        message="Suspicious operation",
        transaction_id=transaction.id,
        client_id=client.id,
    )
    builder = ReportBuilder(
        bank=bank,
        audit_log=audit_log,
        transactions=[transaction],
    )
    return builder, bank, client, rub


def test_day7_builds_client_bank_risk_and_transaction_reports(
    client_factory,
    tmp_path,
):
    builder, _bank, client, _account = make_report_builder(
        client_factory,
        tmp_path,
    )

    client_report = builder.build_client_report(client)
    bank_report = builder.build_bank_report()
    risk_report = builder.build_risk_report()
    transaction_report = builder.build_transactions_report()

    assert client_report["total_balances"] == {
        "RUB": "150",
        "USD": "25",
    }
    assert bank_report["clients_count"] == 2
    assert bank_report["accounts_count"] == 3
    assert bank_report["total_balances"]["RUB"] == "150"
    assert risk_report["suspicious_operations_count"] == 1
    assert len(transaction_report) == 1


def test_day7_exports_text_json_and_csv(client_factory, tmp_path):
    builder, _bank, client, _account = make_report_builder(
        client_factory,
        tmp_path,
    )
    report = builder.build_client_report(client)
    json_path = tmp_path / "nested" / "client.json"
    csv_path = tmp_path / "transactions.csv"
    empty_csv_path = tmp_path / "empty.csv"

    builder.export_to_json(report, json_path)
    builder.export_to_csv(builder.build_transactions_report(), csv_path)
    builder.export_to_csv([], empty_csv_path)

    assert json.loads(json_path.read_text())["client_id"] == str(client.id)

    with csv_path.open(newline="", encoding="utf-8") as file:
        assert len(list(csv.DictReader(file))) == 1

    assert empty_csv_path.exists()
    assert "accounts_count: 2" in builder.to_text(report)


def test_day7_saves_pie_bar_and_balance_charts(client_factory, tmp_path):
    builder, _bank, _client, account = make_report_builder(
        client_factory,
        tmp_path,
    )
    charts_dir = tmp_path / "charts"
    balance_chart = tmp_path / "nested" / "balance.png"

    builder.save_charts(charts_dir)
    builder.save_account_balance_chart(
        account=account,
        file_path=balance_chart,
    )

    for chart in (
        charts_dir / "client_balances.png",
        charts_dir / "transaction_statuses.png",
        charts_dir / "account_balance_history.png",
        balance_chart,
    ):
        assert chart.exists()
        assert chart.stat().st_size > 0


def test_day7_saves_empty_balance_history_chart(client_factory, tmp_path):
    builder, bank, client, _account = make_report_builder(
        client_factory,
        tmp_path,
    )
    empty_account = bank.open_account(
        client=client,
        account_class=BankAccount,
        currency=AccountCurrency.EUR,
    )
    chart_path = tmp_path / "empty_balance.png"

    builder.save_account_balance_chart(
        account=empty_account,
        file_path=chart_path,
    )

    assert chart_path.exists()
    assert chart_path.stat().st_size > 0


def test_balance_chart_uses_readable_time_labels():
    from datetime import datetime

    from src.utils import BANK_TIMEZONE

    timestamp = datetime(
        2026,
        8,
        13,
        20,
        5,
        56,
        640000,
        tzinfo=BANK_TIMEZONE,
    )

    assert _format_chart_time(timestamp) == "13.08.2026\n20:05:56.640"
    positions = _select_label_positions(20)
    assert len(positions) == MAX_TIME_LABELS
    assert positions[0] == 0
    assert positions[-1] == 19


def test_day6_complete_demo_matches_assignment_and_exports_reports(tmp_path):
    output_dir = tmp_path / "demo"
    output_dir.mkdir()
    (output_dir / "audit.jsonl").write_text("stale record\n")
    (
        _bank,
        clients,
        accounts,
        transactions,
        audit_log,
        output_dir,
    ) = run_demo(output_dir)
    statuses = {transaction.status for transaction in transactions}

    assert 5 <= len(clients) <= 10
    assert 10 <= len(accounts) <= 15
    assert 30 <= len(transactions) <= 50
    assert statuses.issuperset(
        {
            # Success, error/suspicion blocking and queue cancellation.
            transaction_status
            for transaction_status in (
                TransactionStatus.COMPLETED,
                TransactionStatus.FAILED,
                TransactionStatus.CANCELLED,
            )
        }
    )
    assert any(
        "queued" in record.message.lower()
        for record in audit_log.records
    )
    assert any(
        record.level is AuditLevel.CRITICAL
        for record in audit_log.records
    )
    assert "stale record" not in (output_dir / "audit.jsonl").read_text()

    expected_files = {
        "audit.jsonl",
        "bank_report.json",
        "bank_report.txt",
        "risk_report.json",
        "transactions.csv",
        "client_balances.png",
        "transaction_statuses.png",
        "account_balance_history.png",
    }
    assert expected_files.issubset(
        {path.name for path in output_dir.iterdir()}
    )
