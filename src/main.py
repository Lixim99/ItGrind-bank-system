from dataclasses import dataclass
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
    OperationPolicy,
    Transaction,
    TransactionProcessor,
    TransactionQueue,
)
from .utils import BANK_TIMEZONE

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "public" / "uploads"


@dataclass(frozen=True)
class DemoResult:
    bank: Bank
    clients: tuple[Client, ...]
    accounts: tuple[BankAccount, ...]
    transactions: tuple[Transaction, ...]
    audit_log: AuditLog
    output_dir: Path


class DemoClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, 12, tzinfo=BANK_TIMEZONE)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def _create_clients(bank: Bank) -> tuple[Client, ...]:
    client_data = (
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
        for first_name, last_name, phone, email, age in client_data
    )

    for client in clients:
        bank.add_client(client)

    return clients


def _create_accounts(
    bank: Bank,
    clients: tuple[Client, ...],
) -> tuple[BankAccount, ...]:
    specifications = (
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
        for client, account_class, currency in specifications
    )

    for account in accounts:
        account.deposit(Decimal("500000"))

    for account in accounts:
        if isinstance(account, InvestmentAccount):
            account.allocate_asset(
                InvestmentAccountActives.stocks,
                Decimal("10000"),
            )

    return accounts


def _make_transaction(
    *,
    sender: BankAccount,
    acceptor: BankAccount,
    amount: str,
    transaction_type: TransactionType,
    clock: DemoClock,
) -> Transaction:
    return Transaction(
        amount=Decimal(amount),
        transaction_type=transaction_type,
        sender=sender,
        acceptor=acceptor,
        created_at=clock(),
    )


def _export_reports(result: DemoResult) -> None:
    builder = ReportBuilder(
        bank=result.bank,
        audit_log=result.audit_log,
        transactions=list(result.transactions),
    )
    output_dir = result.output_dir
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

    for client in result.clients:
        builder.export_to_json(
            builder.build_client_report(client),
            output_dir / f"client_{client.id}.json",
        )

    builder.save_charts(output_dir)
    builder.save_account_balance_chart(
        account=result.accounts[0],
        file_path=output_dir / "account_balance_history.png",
    )


def run_demo(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> DemoResult:
    """Run the complete deterministic scenario required by Day 6."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bank = Bank()
    clients = _create_clients(bank)
    accounts = _create_accounts(bank, clients)
    audit_log = AuditLog(output_dir / "audit.jsonl")
    clock = DemoClock()
    queue = TransactionQueue(clock=clock)
    processor = TransactionProcessor(
        commission_calculator=CommissionCalculator(),
        currency_converter=CurrencyConverter(),
        risk_analyzer=RiskAnalyzer(),
        audit_log=audit_log,
        operation_policy=OperationPolicy(clock=clock),
    )
    transactions: list[Transaction] = []

    def enqueue(
        transaction: Transaction,
        *,
        priority: TransactionPriority = TransactionPriority.NORMAL,
        execute_at: datetime | None = None,
    ) -> None:
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

    def process_ready() -> None:
        while True:
            transaction = queue.get()

            if transaction is None:
                break

            processor.process(transaction)

    # 24 ordinary operations exercise every account and both transfer types.
    for index in range(24):
        enqueue(
            _make_transaction(
                sender=accounts[index % len(accounts)],
                acceptor=accounts[(index + 3) % len(accounts)],
                amount=str(100 + index),
                transaction_type=(
                    TransactionType.EXTERNAL
                    if index % 3 == 0
                    else TransactionType.INTERNAL
                ),
                clock=clock,
            ),
            priority=(
                TransactionPriority.HIGH
                if index % 7 == 0
                else TransactionPriority.NORMAL
            ),
        )

    process_ready()

    # Invalid transfer to a frozen account.
    bank.freeze_account(accounts[9])
    enqueue(
        _make_transaction(
            sender=accounts[1],
            acceptor=accounts[9],
            amount="100",
            transaction_type=TransactionType.INTERNAL,
            clock=clock,
        )
    )
    process_ready()
    bank.unfreeze_account(accounts[9])

    # Invalid transfer with insufficient funds.
    enqueue(
        _make_transaction(
            sender=accounts[3],
            acceptor=accounts[4],
            amount="900000",
            transaction_type=TransactionType.EXTERNAL,
            clock=clock,
        )
    )
    process_ready()

    # Two ordinary operations make the next large transfer frequent and high-risk.
    for acceptor in (accounts[5], accounts[6]):
        enqueue(
            _make_transaction(
                sender=accounts[0],
                acceptor=acceptor,
                amount="50",
                transaction_type=TransactionType.INTERNAL,
                clock=clock,
            )
        )

    enqueue(
        _make_transaction(
            sender=accounts[0],
            acceptor=accounts[7],
            amount="100000",
            transaction_type=TransactionType.EXTERNAL,
            clock=clock,
        )
    )
    process_ready()

    # The thirtieth operation demonstrates scheduling and cancellation.
    delayed = _make_transaction(
        sender=accounts[8],
        acceptor=accounts[2],
        amount="75",
        transaction_type=TransactionType.INTERNAL,
        clock=clock,
    )
    enqueue(delayed, execute_at=clock() + timedelta(minutes=1))
    queue.cancel(delayed.id, "Cancelled in demonstration")
    audit_log.log(
        level=AuditLevel.WARNING,
        message="Scheduled transaction cancelled",
        transaction_id=delayed.id,
        client_id=delayed.sender.client.id,
    )
    clock.advance(timedelta(minutes=1))
    process_ready()

    result = DemoResult(
        bank=bank,
        clients=clients,
        accounts=accounts,
        transactions=tuple(transactions),
        audit_log=audit_log,
        output_dir=output_dir,
    )
    _export_reports(result)
    return result


def main() -> None:
    result = run_demo()
    reporter = AuditReporter(result.audit_log)
    status_counts = {
        status.value: sum(
            transaction.status is status
            for transaction in result.transactions
        )
        for status in TransactionStatus
    }

    print("=== BANK DEMONSTRATION ===")
    print(f"Clients: {len(result.clients)}")
    print(f"Accounts: {len(result.accounts)}")
    print(f"Transactions: {len(result.transactions)}")
    print(f"Statuses: {status_counts}")

    print("\n=== CLIENT ACCOUNTS ===")
    first_client = result.clients[0]

    for account in first_client.accounts:
        print(
            account.account_number,
            account.account_type,
            account.balance,
            account.currency.value,
        )

    print("\n=== TOTAL BALANCES ===")

    for currency in AccountCurrency:
        print(
            currency.value,
            result.bank.get_total_balance(currency),
        )

    print("\n=== TOP 3 RUB CLIENTS ===")

    for position, client in enumerate(
        result.bank.get_clients_ranking(AccountCurrency.RUB)[:3],
        start=1,
    ):
        print(position, client.first_name, client.last_name)

    print("\n=== CLIENT HISTORY ===")

    for transaction in result.transactions:
        if first_client in (
            transaction.sender.client,
            transaction.acceptor.client,
        ):
            print(transaction.id, transaction.status.value)

    print("\n=== SUSPICIOUS OPERATIONS ===")

    for record in reporter.suspicious_operations():
        print(record.level.value, record.message)

    print(f"\nReports saved to: {result.output_dir}")


if __name__ == "__main__":
    main()
