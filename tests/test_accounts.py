from abc import ABC
from decimal import Decimal
from uuid import UUID

import pytest

from src.enums import AccountCurrency, AccountStatus
from src.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)
from src.models import (
    AbstractAccount,
    BankAccount,
    InvestmentAccount,
    PremiumAccount,
    SavingsAccount,
)


def test_abstract_account_is_an_abstract_base_class():
    assert issubclass(AbstractAccount, ABC)
    with pytest.raises(TypeError):
        AbstractAccount()


@pytest.mark.parametrize("currency", list(AccountCurrency))
def test_account_starts_active_with_generated_id(client_factory, currency):
    account = BankAccount(client=client_factory(), currency=currency)

    assert isinstance(account.id, UUID)
    assert account.currency is currency
    assert account.status is AccountStatus.ACTIVE
    assert account.balance == Decimal("0")


def test_deposit_and_withdrawal_change_protected_balance(client_factory):
    account = BankAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )

    account.deposit(Decimal("1000.00"))
    account.withdraw(Decimal("250.00"))

    assert account.balance == Decimal("747.50")


@pytest.mark.parametrize(
    "amount",
    [Decimal("0"), Decimal("-1"), Decimal("Infinity")],
)
def test_account_rejects_invalid_amounts(client_factory, amount):
    account = BankAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )

    with pytest.raises(InvalidOperationError):
        account.deposit(amount)


def test_account_rejects_withdrawal_without_enough_money(client_factory):
    account = BankAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )
    account.deposit(Decimal("10"))

    with pytest.raises(InsufficientFundsError):
        account.withdraw(Decimal("20"))


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (AccountStatus.FROZEN, AccountFrozenError),
        (AccountStatus.CLOSED, AccountClosedError),
    ],
)
def test_inactive_account_rejects_operations(
    client_factory,
    status,
    error,
):
    account = BankAccount(
        client=client_factory(),
        currency=AccountCurrency.USD,
    )
    account.change_account_status(status)

    with pytest.raises(error):
        account.deposit(Decimal("10"))
    with pytest.raises(error):
        account.withdraw(Decimal("10"))


def test_account_string_contains_required_safe_fields(client_factory):
    account = BankAccount(
        client=client_factory(),
        currency=AccountCurrency.EUR,
    )
    account.deposit(Decimal("125.50"))

    rendered = str(account)

    assert "BankAccount" in rendered
    assert account.client.first_name in rendered
    assert str(account.id)[-4:] in rendered
    assert AccountStatus.ACTIVE.value in rendered
    assert "125.50" in rendered
    assert AccountCurrency.EUR.value in rendered
    assert str(account.id) not in rendered


def test_savings_account_preserves_minimum_and_applies_interest(client_factory):
    account = SavingsAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )
    account.deposit(Decimal("1000.00"))

    account.apply_monthly_interest()
    account.withdraw(Decimal("100.00"))

    assert account.balance == Decimal("949.00")
    assert account.get_account_info()["Monthly Interest Rate"] == Decimal("0.05")
    with pytest.raises(InvalidOperationError):
        account.withdraw(Decimal("850.00"))


def test_premium_account_supports_fixed_fee_and_overdraft(client_factory):
    account = PremiumAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )
    account.deposit(Decimal("500.00"))

    account.withdraw(Decimal("700.00"))

    assert account.balance == Decimal("-201.00")
    assert account.get_account_info()["Fixed Commission"] == Decimal("1.00")


def test_premium_account_enforces_overdraft_limit(client_factory):
    account = PremiumAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )

    with pytest.raises(InsufficientFundsError):
        account.withdraw(Decimal("1000.00"))


def test_investment_account_exposes_assets_and_growth(client_factory):
    account = InvestmentAccount(
        client=client_factory(),
        currency=AccountCurrency.CNY,
    )
    account.deposit(Decimal("1000.00"))

    account.project_yearly_growth()

    assert account.balance == Decimal("1130.0000")
    assert account.get_account_info()["ACTIVES"] == ["stocks", "bonds", "etf"]
    assert str(account).startswith("InvestmentAccount(")
