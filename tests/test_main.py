from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.base import Base
from src.enums import AccountCurrency, AccountStatus, ClientStatus
from src.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)
from src.models import (
    Bank,
    BankAccount,
    Client,
    InvestmentAccount,
    PremiumAccount,
    SavingsAccount,
)


def make_client(number: int = 1, *, password_hash: str = "unused") -> Client:
    return Client(
        age=30,
        first_name=f"Client{number}",
        last_name="Test",
        middle_name=None,
        email=f"client{number}@example.com",
        phone=f"+700000000{number:02d}",
        password_hash=password_hash,
        status=ClientStatus.ACTIVE.value,
        failed_login_attempts=0,
        is_suspicious=False,
    )


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as current_session:
        yield current_session


class TestBankAccount:
    def test_create_active_and_frozen_accounts(self):
        client = make_client()
        active_account = BankAccount(
            client=client,
            currency=AccountCurrency.RUB,
        )
        frozen_account = BankAccount(
            client=client,
            currency="USD",
        )
        frozen_account.change_account_status(AccountStatus.FROZEN)

        assert active_account.status is AccountStatus.ACTIVE
        assert active_account.balance == Decimal("0.00")
        assert frozen_account.status is AccountStatus.FROZEN
        assert frozen_account.currency is AccountCurrency.USD

    def test_frozen_and_closed_accounts_reject_operations(self):
        account = BankAccount(
            client=make_client(),
            currency=AccountCurrency.RUB,
        )
        account.change_account_status(AccountStatus.FROZEN)

        with pytest.raises(AccountFrozenError):
            account.deposit(100)
        with pytest.raises(AccountFrozenError):
            account.withdraw(50)

        account.change_account_status(AccountStatus.CLOSED)
        with pytest.raises(AccountClosedError):
            account.deposit(100)

    def test_valid_deposit_and_withdrawal_use_decimal(self):
        account = BankAccount(
            client=make_client(),
            currency=AccountCurrency.RUB,
        )

        account.deposit(100.0)
        account.withdraw(40)

        assert account.balance == Decimal("59.60")

    @pytest.mark.parametrize("amount", [0, -1, True])
    def test_invalid_deposit_amount(self, amount):
        account = BankAccount(
            client=make_client(),
            currency=AccountCurrency.RUB,
        )

        with pytest.raises((InvalidOperationError, TypeError)):
            account.deposit(amount)


class TestSavingsAccount:
    def test_interest_and_withdrawal(self):
        first_account = SavingsAccount(
            client=make_client(1),
            currency=AccountCurrency.RUB,
        )
        second_account = SavingsAccount(
            client=make_client(2),
            currency=AccountCurrency.USD,
        )

        first_account.deposit(1000)
        second_account.deposit(200)
        first_account.apply_monthly_interest()
        second_account.withdraw(50)
        second_account.apply_monthly_interest()

        assert first_account.balance == Decimal("1050.0000")
        assert second_account.balance == Decimal("156.9750")
        assert (
            first_account.get_account_info()["Monthly Interest Rate"]
            == Decimal("0.05")
        )

    def test_minimum_balance_rules(self):
        account_without_minimum = SavingsAccount(
            client=make_client(1),
            currency=AccountCurrency.RUB,
        )
        account_without_minimum.deposit(99)

        with pytest.raises(InvalidOperationError):
            account_without_minimum.apply_monthly_interest()

        account_with_minimum = SavingsAccount(
            client=make_client(2),
            currency=AccountCurrency.RUB,
        )
        account_with_minimum.deposit(150)

        with pytest.raises(InvalidOperationError):
            account_with_minimum.withdraw(50)

        assert account_with_minimum.balance == Decimal("150.00")


class TestPremiumAccount:
    def test_fixed_commission_and_overdraft(self):
        account_with_large_withdrawal = PremiumAccount(
            client=make_client(1),
            currency=AccountCurrency.RUB,
        )
        account_with_overdraft = PremiumAccount(
            client=make_client(2),
            currency=AccountCurrency.USD,
        )

        account_with_large_withdrawal.deposit(3000)
        account_with_large_withdrawal.withdraw(1500)
        account_with_overdraft.deposit(500)
        account_with_overdraft.withdraw(1000)

        assert account_with_large_withdrawal.balance == Decimal("1499.00")
        assert account_with_overdraft.balance == Decimal("-501.00")
        assert (
            account_with_overdraft.get_account_info()["Fixed Commission"]
            == Decimal("1.00")
        )

    def test_limits(self):
        account_over_withdrawal_limit = PremiumAccount(
            client=make_client(1),
            currency=AccountCurrency.RUB,
        )
        account_over_withdrawal_limit.deposit(10_000)

        with pytest.raises(InvalidOperationError):
            account_over_withdrawal_limit.withdraw(5000)

        account_over_overdraft_limit = PremiumAccount(
            client=make_client(2),
            currency=AccountCurrency.RUB,
        )
        with pytest.raises(InsufficientFundsError):
            account_over_overdraft_limit.withdraw(1000)


class TestInvestmentAccount:
    def test_yearly_growth(self):
        account = InvestmentAccount(
            client=make_client(),
            currency=AccountCurrency.RUB,
        )

        account.deposit(1000)
        account.project_yearly_growth()
        account.withdraw(100)

        assert account.balance == Decimal("1029.0000")
        assert account.get_account_info()["ACTIVES"] == [
            "stocks",
            "bonds",
            "etf",
        ]

    def test_growth_requires_positive_balance(self):
        account = InvestmentAccount(
            client=make_client(),
            currency=AccountCurrency.CNY,
        )

        with pytest.raises(InvalidOperationError):
            account.project_yearly_growth()


class TestBank:
    def test_add_client_rejects_duplicate_phone_or_email(self, session):
        bank = Bank(session)
        client = make_client(1)
        bank.add_client(client)

        duplicate_phone = make_client(2)
        duplicate_phone.phone = client.phone
        with pytest.raises(ValueError):
            bank.add_client(duplicate_phone)

        duplicate_email = make_client(3)
        duplicate_email.email = client.email
        with pytest.raises(ValueError):
            bank.add_client(duplicate_email)

    def test_authentication_blocks_after_three_failures(self, session):
        bank = Bank(session)
        client = Client.create(
            age=30,
            first_name="Alice",
            last_name="Test",
            email="alice@example.com",
            phone="+70000000100",
            password="secret",
        )
        bank.add_client(client)

        assert bank.authenticate_client(client.phone, "wrong") is None
        assert bank.authenticate_client(client.phone, "secret") is client
        assert client.failed_login_attempts == 0

        for _ in range(bank.MAX_FAILED_LOGIN_ATTEMPTS):
            assert bank.authenticate_client(client.phone, "wrong") is None

        assert client.is_blocked
        assert client.is_suspicious
        assert client.failed_login_attempts == 3
        assert bank.authenticate_client(client.phone, "secret") is None
        assert client.failed_login_attempts == 3

    def test_account_search_totals_and_ranking(self, session):
        bank = Bank(session)
        first_client = make_client(1)
        second_client = make_client(2)
        bank.add_client(first_client)
        bank.add_client(second_client)

        first_rub = bank.open_account(BankAccount(
            client=first_client,
            currency=AccountCurrency.RUB,
        ))
        second_rub = bank.open_account(BankAccount(
            client=second_client,
            currency=AccountCurrency.RUB,
        ))
        bank.open_account(BankAccount(
            client=second_client,
            currency=AccountCurrency.USD,
        ))
        first_rub.deposit(125.50)
        second_rub.deposit(300)
        bank.save_account_transact(first_rub)
        bank.save_account_transact(second_rub)

        assert bank.search_accounts(
            currency=AccountCurrency.RUB,
            client=first_client,
        ) == [first_rub]
        assert bank.get_total_balance(AccountCurrency.RUB) == Decimal("425.50")
        assert bank.get_total_balance(
            AccountCurrency.RUB,
            first_client,
        ) == Decimal("125.50")
        assert bank.get_clients_ranking(AccountCurrency.RUB) == [
            second_client,
            first_client,
        ]

    def test_account_subclass_is_persisted_polymorphically(self, session):
        bank = Bank(session)
        client = make_client()
        bank.add_client(client)

        account = bank.open_account(SavingsAccount(
            client=client,
            currency=AccountCurrency.USD,
        ))
        account_id = account.id
        session.expunge_all()

        loaded_account = session.get(BankAccount, account_id)

        assert isinstance(loaded_account, SavingsAccount)
        assert loaded_account.account_type == "savings_account"

    def test_account_status_transitions(self, session):
        bank = Bank(session)
        client = make_client()
        bank.add_client(client)
        account = bank.open_account(BankAccount(
            client=client,
            currency=AccountCurrency.RUB,
        ))

        bank.freeze_account(account)
        assert account.status is AccountStatus.FROZEN
        with pytest.raises(InvalidOperationError):
            bank.freeze_account(account)

        bank.unfreeze_account(account)
        assert account.status is AccountStatus.ACTIVE
        with pytest.raises(InvalidOperationError):
            bank.unfreeze_account(account)

        bank.close_account(account)
        assert account.status is AccountStatus.CLOSED
        with pytest.raises(InvalidOperationError):
            bank.close_account(account)
        with pytest.raises(InvalidOperationError):
            bank.freeze_account(account)

    def test_blocked_and_foreign_clients_cannot_open_accounts(self, session):
        bank = Bank(session)
        blocked_client = make_client(1)
        bank.add_client(blocked_client)
        blocked_client.status = ClientStatus.BLOCKED.value
        session.flush()

        with pytest.raises(InvalidOperationError):
            bank.open_account(BankAccount(
                client=blocked_client,
                currency=AccountCurrency.RUB,
            ))

        foreign_client = make_client(2)
        foreign_client.id = uuid4()
        with pytest.raises(ValueError):
            bank.open_account(BankAccount(
                client=foreign_client,
                currency=AccountCurrency.RUB,
            ))

    def test_blocked_client_cannot_use_existing_account(self, session):
        bank = Bank(session)
        client = make_client()
        bank.add_client(client)
        account = bank.open_account(BankAccount(
            client=client,
            currency=AccountCurrency.RUB,
        ))
        client.status = ClientStatus.BLOCKED.value
        session.flush()

        with pytest.raises(InvalidOperationError):
            account.deposit(100)
        with pytest.raises(InvalidOperationError):
            account.withdraw(100)
        with pytest.raises(InvalidOperationError):
            bank.save_account_transact(account)

        assert account.balance == Decimal("0.00")

    def test_foreign_account_cannot_be_changed(self, session):
        bank = Bank(session)
        foreign_account = BankAccount(
            client=make_client(),
            currency=AccountCurrency.RUB,
        )
        foreign_account.id = uuid4()

        with pytest.raises(ValueError):
            bank.freeze_account(foreign_account)
