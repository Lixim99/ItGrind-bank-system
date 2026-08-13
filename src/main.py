from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from .audit import AuditLog, AuditReporter, RiskAnalyzer
from .bank import Bank
from .enums import (
    AccountCurrency,
    TransactionPriority,
    TransactionType,
)
from .models import Client, InvestmentAccount, PremiumAccount, SavingsAccount
from .report import ReportBuilder
from .transaction import (
    CommissionCalculator,
    CurrencyConverter,
    OperationPolicy,
    Transaction,
    TransactionProcessor,
    TransactionQueue,
)
from .utils import bank_now

PROJECT_ROOT = Path(__file__).resolve().parent.parent

UPLOAD_DIR = (
    PROJECT_ROOT
    / "public"
    / "uploads"
)

UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def main() -> None:
    # ==========================================
    # 0. Создаём клиентов
    # ==========================================

    max_client = Client(
        first_name="Max",
        last_name="Litvinov",
        middle_name="Alexandrovich",
        email="max@example.com",
        phone="+79990000001",
        password="password",
        age=26,
    )

    john_client = Client(
        first_name="John",
        last_name="Smith",
        email="john@example.com",
        phone="+79990000002",
        password="password",
        age=35,
    )

    alex_client = Client(
        first_name="Alex",
        last_name="Ivanov",
        email="alex@example.com",
        phone="+79990000003",
        password="password",
        age=25,
    )

    alice_client = Client(
        first_name="Alice",
        last_name="Testova",
        email="alice@example.com",
        phone="+79990000004",
        password="password",
        age=27,
    )

    tom_client = Client(
        first_name="Tom",
        last_name="Crawly",
        email="tom@example.com",
        phone="+79990000005",
        password="password",
        age=23,
    )

    # ==========================================
    # 1. Добавляем клиентов в банк
    # ==========================================

    bank = Bank()

    bank.add_client(max_client)
    bank.add_client(john_client)
    bank.add_client(alex_client)
    bank.add_client(alice_client)
    bank.add_client(tom_client)

    # ==========================================
    # 2. Открываем счета
    # ==========================================

    # Сделать account_type
    max_rub = bank.open_account(
        client=max_client,
        currency=AccountCurrency.RUB,
        account_class=InvestmentAccount
    )

    max_usd = bank.open_account(
        client=max_client,
        currency=AccountCurrency.USD,
        account_class=SavingsAccount
    )

    alex_rub = bank.open_account(
        client=alex_client,
        currency=AccountCurrency.RUB,
        account_class=PremiumAccount
    )

    alex_eur = bank.open_account(
        client=alex_client,
        currency=AccountCurrency.EUR,
        account_class=SavingsAccount
    )

    john_rub = bank.open_account(
        client=john_client,
        currency=AccountCurrency.RUB,
        account_class=InvestmentAccount
    )

    # Итого по ТЗ нужно 10–15 счетов.

    # ==========================================
    # 3. Начальные балансы
    # ==========================================

    max_rub.deposit(Decimal(500000))
    max_usd.deposit(Decimal(5000))

    alex_rub.deposit(Decimal(300000))
    alex_eur.deposit(Decimal(3000))

    john_rub.deposit(Decimal(100000))

    # ==========================================
    # 4. Создаём инфраструктуру транзакций
    # ==========================================
    queue = TransactionQueue()

    audit_log = AuditLog(UPLOAD_DIR / "audit.log")

    processor = TransactionProcessor(
        commission_calculator=CommissionCalculator(),
        currency_converter=CurrencyConverter(),
        risk_analyzer=RiskAnalyzer(),
        audit_log=audit_log,
        operation_policy=OperationPolicy()
    )

    # ==========================================
    # 5. Создаём обычные транзакции
    # ==========================================

    transaction_1 = Transaction(
        amount=Decimal(10000),
        transaction_type=TransactionType.INTERNAL,
        sender=max_rub,
        acceptor=alex_rub,
    )

    transaction_2 = Transaction(
        amount=Decimal(500),
        transaction_type=TransactionType.EXTERNAL,
        sender=max_usd,
        acceptor=alex_eur,
    )

    queue.put(
        transaction=transaction_1,
        priority=TransactionPriority.NORMAL,
    )

    queue.put(
        transaction=transaction_2,
        priority=TransactionPriority.HIGH,
    )

    # ==========================================
    # 6. Отложенная транзакция
    # ==========================================

    delayed_transaction = Transaction(
        amount=Decimal(1000),
        transaction_type=TransactionType.INTERNAL,
        sender=alex_rub,
        acceptor=john_rub,
    )

    queue.put(
        transaction=delayed_transaction,
        priority=TransactionPriority.NORMAL,
        execute_at=(bank_now() + timedelta(seconds=1)),
    )

    # ==========================================
    # 7. Ошибочная транзакция
    # ==========================================

    insufficient_funds_transaction = Transaction(
        amount=Decimal(999999999),
        transaction_type=TransactionType.INTERNAL,
        sender=john_rub,
        acceptor=max_rub,
    )

    queue.put(
        transaction=insufficient_funds_transaction,
        priority=TransactionPriority.NORMAL,
    )

    # ==========================================
    # 8. Подозрительная транзакция
    # ==========================================

    suspicious_transaction = Transaction(
        amount=Decimal(500000),
        transaction_type=TransactionType.EXTERNAL,
        sender=max_rub,
        acceptor=john_rub,
    )

    queue.put(
        transaction=suspicious_transaction,
        priority=TransactionPriority.HIGH,
    )

    transactions = [
        transaction_1,
        transaction_2,
        delayed_transaction,
        insufficient_funds_transaction,
        suspicious_transaction,
    ]

    # ==========================================
    # 9. Обрабатываем очередь
    # ==========================================

    while not queue.is_empty():
        transaction = queue.get()

        if transaction is None:
            # Сейчас есть scheduled операции,
            # но их execute_at ещё не наступил.
            continue

        print(
            f"Processing transaction: {transaction.id}"
        )

        processor.process(transaction)

        print(
            f"Status: {transaction.status.value}"
        )

        if transaction.reason is not None:
            print(
                f"Reason: {transaction.reason}"
            )

    # ==========================================
    # 10. Пользовательские сценарии
    # ==========================================

    print("\n=== CLIENT ACCOUNTS ===")

    for account in max_client.accounts:
        print(
            account.id,
            account.currency.value,
            account.balance,
        )

    # ==========================================
    # 11. Общий баланс банка
    # ==========================================

    print("\n=== TOTAL BALANCE ===")

    total_balance_rub = bank.get_total_balance(AccountCurrency.RUB)
    total_balance_eur = bank.get_total_balance(AccountCurrency.EUR)

    print(f"RUB:{total_balance_rub}\n")
    print(f"EUR:{total_balance_eur}\n")

    # ==========================================
    # 12. Топ клиентов
    # ==========================================

    print("\n=== TOP 3 CLIENTS ===")

    top_rub_clients = bank.get_clients_ranking(
        currency=AccountCurrency.RUB)[:3]
    top_eur_clients = bank.get_clients_ranking(
        currency=AccountCurrency.RUB)[:3]

    print("\nТоп рублевых аккаунтов")
    for position, client in enumerate(
        top_rub_clients,
        start=1,
    ):
        print(
            position,
            client.first_name,
            client.last_name,
        )

    print("\nТоп евро аккаунтов")
    for position, client in enumerate(
        top_eur_clients,
        start=1,
    ):
        print(
            position,
            client.first_name,
            client.last_name,
        )

    # ==========================================
    # 13. Подозрительные операции
    # ==========================================

    print("\n=== SUSPICIOUS OPERATIONS ===")

    reporter = AuditReporter(audit_log)

    suspicious = reporter.suspicious_operations()

    for record in suspicious:
        print(
            record.timestamp,
            record.level.value,
            record.message,
        )

    # ==========================================
    # 14. Статистика ошибок
    # ==========================================

    print("\n=== ERROR STATISTICS ===")

    statistics = reporter.error_statistics()

    for error, amount in statistics.items():
        print(
            error,
            amount,
        )

    #
    # = 15 =
    #
    print("\n Report:")
    report_builder = ReportBuilder(
        bank=bank,
        audit_log=audit_log,
        transactions=transactions
    )

    bank_report = (
        report_builder.build_bank_report()
    )

    report_builder.export_to_json(
        bank_report,
        UPLOAD_DIR / "bank_report.json",
    )

    bank_report_text = report_builder.to_text(
        bank_report
    )

    (
        UPLOAD_DIR / "bank_report.txt"
    ).write_text(
        bank_report_text,
        encoding="utf-8",
    )

    risk_report = (
        report_builder.build_risk_report()
    )

    report_builder.export_to_json(
        risk_report,
        UPLOAD_DIR / "risk_report.json",
    )

    for client in bank.clients.values():
        client_report = (
            report_builder.build_client_report(
                client
            )
        )

        report_builder.export_to_json(
            client_report,
            (
                UPLOAD_DIR
                / f"client_{client.id}.json"
            ),
        )

    transactions_report = (
        report_builder.build_transactions_report()
    )

    report_builder.export_to_csv(
        transactions_report,
        UPLOAD_DIR / "transactions.csv",
    )

    report_builder.save_charts(
        UPLOAD_DIR,
        currency=AccountCurrency.RUB
    )

    report_builder.save_account_balance_chart(
        account=max_rub,
        file_path=(
            UPLOAD_DIR
            / "max_rub_balance_history.png"
        ),
    )


if __name__ == "__main__":
    main()
