from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from .audit import AuditLog, AuditReporter, RiskAnalyzer
from .bank import Bank
from .enums import (
    AccountCurrency,
    AuditLevel,
    InvestmentAccountActives,
    TransactionPriority,
    TransactionStatus,
    TransactionType,
)
from .models import (
    BankAccount,
    Client,
    InvestmentAccount,
    PremiumAccount,
    SavingsAccount,
)
from .report import ReportBuilder
from .transaction import (
    CommissionCalculator,
    CurrencyConverter,
    Transaction,
    TransactionProcessor,
    TransactionQueue,
)
from .utils import BANK_TIMEZONE

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "public" / "uploads"
DEMO_TIME = datetime(2026, 1, 1, 12, tzinfo=BANK_TIMEZONE)
DemoData = tuple[
    Bank,
    tuple[Client, ...],
    tuple[BankAccount, ...],
    tuple[Transaction, ...],
    AuditLog,
    Path,
]


def create_clients(bank: Bank) -> tuple[Client, ...]:
    """Создать и зарегистрировать пять клиентов."""
    clients_data = (
        ("Max", "Litvinov", "+79990000001", "max@example.com", 26),
        ("John", "Smith", "+79990000002", "john@example.com", 35),
        ("Alex", "Ivanov", "+79990000003", "alex@example.com", 25),
        ("Alice", "Testova", "+79990000004", "alice@example.com", 27),
        ("Tom", "Crawly", "+79990000005", "tom@example.com", 23),
    )
    clients = tuple(
        Client(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            age=age,
            password="demo-password",
        )
        for first_name, last_name, phone, email, age in clients_data
    )

    for client in clients:
        bank.add_client(client)

    return clients


def create_accounts(
    bank: Bank,
    clients: tuple[Client, ...],
) -> tuple[BankAccount, ...]:
    """Открыть десять счетов разных типов."""
    accounts_data = (
        (clients[0], InvestmentAccount, AccountCurrency.RUB),
        (clients[0], SavingsAccount, AccountCurrency.USD),
        (clients[1], InvestmentAccount, AccountCurrency.RUB),
        (clients[1], BankAccount, AccountCurrency.EUR),
        (clients[2], PremiumAccount, AccountCurrency.RUB),
        (clients[2], SavingsAccount, AccountCurrency.EUR),
        (clients[3], BankAccount, AccountCurrency.RUB),
        (clients[3], PremiumAccount, AccountCurrency.CNY),
        (clients[4], SavingsAccount, AccountCurrency.RUB),
        (clients[4], InvestmentAccount, AccountCurrency.KZT),
    )
    accounts = tuple(
        bank.open_account(
            client=client,
            account_class=account_class,
            currency=currency,
        )
        for client, account_class, currency in accounts_data
    )

    for account in accounts:
        account.deposit(Decimal("500000"))

        # Добавляем виртуальный актив в инвестиционный портфель.
        if isinstance(account, InvestmentAccount):
            account.allocate_asset(
                InvestmentAccountActives.stocks,
                Decimal("10000"),
            )

    return accounts


def create_transaction(
    sender: BankAccount,
    acceptor: BankAccount,
    amount: str,
    transaction_type: TransactionType = TransactionType.INTERNAL,
) -> Transaction:
    """Создать транзакцию для демонстрации."""
    return Transaction(
        amount=Decimal(amount),
        transaction_type=transaction_type,
        sender=sender,
        acceptor=acceptor,
        created_at=DEMO_TIME,
    )


def enqueue_transaction(
    transaction: Transaction,
    transactions: list[Transaction],
    queue: TransactionQueue,
    audit_log: AuditLog,
    *,
    priority: TransactionPriority = TransactionPriority.NORMAL,
    execute_at: datetime | None = None,
) -> None:
    """Добавить операцию в очередь и аудит."""
    transactions.append(transaction)
    queue.put(
        transaction=transaction,
        priority=priority,
        execute_at=execute_at,
    )
    audit_log.log(
        level=AuditLevel.INFO,
        message="Transaction queued",
        transaction_id=transaction.id,
        client_id=transaction.sender.client.id,
        metadata={"priority": priority.name},
    )


def process_ready_transactions(
    queue: TransactionQueue,
    processor: TransactionProcessor,
) -> None:
    """Обработать готовые операции."""
    while True:
        transaction = queue.get()

        if transaction is None:
            break

        processor.process(transaction)


def export_reports(
    *,
    bank: Bank,
    clients: tuple[Client, ...],
    accounts: tuple[BankAccount, ...],
    transactions: list[Transaction],
    audit_log: AuditLog,
    output_dir: Path,
) -> None:
    """Сохранить отчёты и три вида графиков из ТЗ."""
    builder = ReportBuilder(
        bank=bank,
        audit_log=audit_log,
        transactions=transactions,
    )
    bank_report = builder.build_bank_report()

    builder.export_to_json(bank_report, output_dir / "bank_report.json")
    (output_dir / "bank_report.txt").write_text(
        builder.to_text(bank_report),
        encoding="utf-8",
    )
    builder.export_to_json(
        builder.build_risk_report(),
        output_dir / "risk_report.json",
    )
    builder.export_to_csv(
        builder.build_transactions_report(),
        output_dir / "transactions.csv",
    )

    for number, client in enumerate(clients, start=1):
        builder.export_to_json(
            builder.build_client_report(client),
            output_dir / f"client_{number}.json",
        )

    builder.save_charts(
        output_dir,
        account=accounts[0],
    )


def run_demo(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> DemoData:
    """Запустить полный сценарий Дня 6."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = output_dir / "audit.jsonl"

    # Не смешиваем аудит нескольких запусков.
    audit_path.write_text("", encoding="utf-8")

    bank = Bank()
    clients = create_clients(bank)
    accounts = create_accounts(bank, clients)
    audit_log = AuditLog(audit_path)

    # С фиксированным временем результат воспроизводим.
    def demo_clock() -> datetime:
        return DEMO_TIME

    queue = TransactionQueue(clock=demo_clock)
    processor = TransactionProcessor(
        commission_calculator=CommissionCalculator(),
        currency_converter=CurrencyConverter(),
        risk_analyzer=RiskAnalyzer(),
        audit_log=audit_log,
    )
    transactions: list[Transaction] = []

    # Обычные переводы охватывают все счета и валюты.
    for index in range(24):
        transaction_type = (
            TransactionType.EXTERNAL
            if index % 3 == 0
            else TransactionType.INTERNAL
        )
        priority = (
            TransactionPriority.HIGH
            if index % 7 == 0
            else TransactionPriority.NORMAL
        )
        enqueue_transaction(
            create_transaction(
                accounts[index % len(accounts)],
                accounts[(index + 3) % len(accounts)],
                str(100 + index),
                transaction_type,
            ),
            transactions,
            queue,
            audit_log,
            priority=priority,
        )

    process_ready_transactions(queue, processor)

    # Ошибка №1: получатель заморожен.
    bank.freeze_account(accounts[9])
    enqueue_transaction(
        create_transaction(accounts[1], accounts[9], "100"),
        transactions,
        queue,
        audit_log,
    )
    process_ready_transactions(queue, processor)
    bank.unfreeze_account(accounts[9])

    # Ошибка №2: недостаточно денег.
    enqueue_transaction(
        create_transaction(
            accounts[3],
            accounts[4],
            "900000",
            TransactionType.EXTERNAL,
        ),
        transactions,
        queue,
        audit_log,
    )
    process_ready_transactions(queue, processor)

    # Частые переводы повышают риск.
    for acceptor in (accounts[5], accounts[6]):
        enqueue_transaction(
            create_transaction(accounts[0], acceptor, "50"),
            transactions,
            queue,
            audit_log,
        )

    enqueue_transaction(
        create_transaction(
            accounts[0],
            accounts[7],
            "100000",
            TransactionType.EXTERNAL,
        ),
        transactions,
        queue,
        audit_log,
    )
    process_ready_transactions(queue, processor)

    # Последнюю операцию откладываем и отменяем.
    delayed = create_transaction(accounts[8], accounts[2], "75")
    enqueue_transaction(
        delayed,
        transactions,
        queue,
        audit_log,
        execute_at=DEMO_TIME + timedelta(minutes=1),
    )
    queue.cancel(delayed.id, "Cancelled in demonstration")
    audit_log.log(
        level=AuditLevel.WARNING,
        message="Scheduled transaction cancelled",
        transaction_id=delayed.id,
        client_id=delayed.sender.client.id,
    )

    export_reports(
        bank=bank,
        clients=clients,
        accounts=accounts,
        transactions=transactions,
        audit_log=audit_log,
        output_dir=output_dir,
    )

    return (
        bank,
        clients,
        accounts,
        tuple(transactions),
        audit_log,
        output_dir,
    )


def print_demo_result(
    bank: Bank,
    clients: tuple[Client, ...],
    accounts: tuple[BankAccount, ...],
    transactions: tuple[Transaction, ...],
    audit_log: AuditLog,
    output_dir: Path,
) -> None:
    """Показать пользовательские сценарии из ТЗ."""
    status_counts = {
        status.value: sum(
            transaction.status is status
            for transaction in transactions
        )
        for status in TransactionStatus
    }

    print("=== BANK DEMONSTRATION ===")
    print(f"Clients: {len(clients)}")
    print(f"Accounts: {len(accounts)}")
    print(f"Transactions: {len(transactions)}")
    print(f"Statuses: {status_counts}")

    print("\n=== CLIENT ACCOUNTS ===")
    first_client = clients[0]

    for account in first_client.accounts:
        print(
            account.account_number,
            account.account_type,
            account.balance,
            account.currency.value,
        )

    print("\n=== TOTAL BALANCES ===")

    for currency in AccountCurrency:
        print(currency.value, bank.get_total_balance(currency))

    print("\n=== TOP 3 RUB CLIENTS ===")

    for position, client in enumerate(
        bank.get_clients_ranking(AccountCurrency.RUB)[:3],
        start=1,
    ):
        print(position, client.first_name, client.last_name)

    print("\n=== CLIENT HISTORY ===")

    for transaction in transactions:
        if first_client in (
            transaction.sender.client,
            transaction.acceptor.client,
        ):
            print(transaction.id, transaction.status.value)

    print("\n=== SUSPICIOUS OPERATIONS ===")

    for record in AuditReporter(audit_log).suspicious_operations():
        print(record.level.value, record.message)

    print(f"\nReports saved to: {output_dir}")
