from abc import ABC
from decimal import Decimal
from uuid import UUID

import pytest

from src.enums import (
    AccountCurrency,
    AccountStatus,
    InvestmentAccountActives,
)
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


def test_day1_abstract_account_defines_required_contract():
    assert issubclass(AbstractAccount, ABC)
    assert AbstractAccount.__abstractmethods__ == {
        "deposit",
        "withdraw",
        "get_account_info",
    }

    with pytest.raises(TypeError):
        AbstractAccount()


@pytest.mark.parametrize("currency", list(AccountCurrency))
def test_day1_account_generates_short_number_and_supports_currency(
    client_factory,
    currency,
):
    account = BankAccount(client=client_factory(), currency=currency)

    assert isinstance(account.id, UUID)
    assert len(account.account_number) == 8
    assert account.account_number.isalnum()
    assert account.currency is currency
    assert account.status is AccountStatus.ACTIVE
    assert account.balance == Decimal("0")


def test_day1_account_accepts_valid_explicit_number(client_factory):
    account = BankAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
        account_number="ABCD1234",
    )

    assert account.account_number == "ABCD1234"


@pytest.mark.parametrize(
    "amount",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("Infinity"),
        Decimal("NaN"),
        100,
    ],
)
def test_day1_account_rejects_invalid_amounts(client_factory, amount):
    account = BankAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )

    with pytest.raises(InvalidOperationError):
        account.deposit(amount)


def test_day1_deposit_and_withdrawal_apply_percentage_commission(
    client_factory,
):
    account = BankAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )
    account.deposit(Decimal("1000.00"))
    account.withdraw(Decimal("250.00"))

    assert account.balance == Decimal("747.50")
    assert len(account.balance_history) == 2


@pytest.mark.parametrize(
    "account_class",
    [BankAccount, SavingsAccount, PremiumAccount, InvestmentAccount],
)
def test_day3_night_policy_blocks_direct_deposit_and_withdrawal(
    client_factory,
    bank_clock,
    account_class,
):
    account = account_class(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )
    account.deposit(Decimal("1000"))
    balance_before = account.balance
    history_before = account.balance_history
    bank_clock.now = bank_clock.now.replace(hour=1)

    with pytest.raises(InvalidOperationError, match="00:00 to 05:00"):
        account.deposit(Decimal("100"))

    with pytest.raises(InvalidOperationError, match="00:00 to 05:00"):
        account.withdraw(Decimal("100"))

    assert account.balance == balance_before
    assert account.balance_history == history_before


@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        (AccountStatus.FROZEN, AccountFrozenError),
        (AccountStatus.CLOSED, AccountClosedError),
    ],
)
def test_day1_inactive_accounts_reject_all_operations(
    client_factory,
    status,
    expected_error,
):
    account = BankAccount(
        client=client_factory(),
        currency=AccountCurrency.USD,
    )
    account.change_account_status(status)

    with pytest.raises(expected_error):
        account.deposit(Decimal("10"))

    with pytest.raises(expected_error):
        account.withdraw(Decimal("10"))


def test_day1_account_rejects_insufficient_funds_and_base_limit(
    client_factory,
):
    account = BankAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )
    account.deposit(Decimal("5000"))

    with pytest.raises(InvalidOperationError, match="Withdrawal limit"):
        account.withdraw(Decimal("1001"))

    empty_account = BankAccount(
        client=client_factory(2),
        currency=AccountCurrency.RUB,
    )

    with pytest.raises(InsufficientFundsError):
        empty_account.withdraw(Decimal("1"))


def test_day1_string_contains_only_safe_required_fields(client_factory):
    account = BankAccount(
        client=client_factory(),
        currency=AccountCurrency.EUR,
        account_number="SAFE1234",
    )
    account.deposit(Decimal("125.50"))

    rendered = str(account)

    assert "BankAccount" in rendered
    assert "Client1 Test" in rendered
    assert "***1234" in rendered
    assert "SAFE1234" not in rendered
    assert "active" in rendered
    assert "125.50" in rendered
    assert "EUR" in rendered


def test_day2_savings_preserves_minimum_and_records_interest(
    client_factory,
):
    account = SavingsAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )
    account.deposit(Decimal("1000.00"))
    account.apply_monthly_interest()
    account.withdraw(Decimal("100.00"))

    assert account.min_balance == Decimal("100.00")
    assert account.monthly_interest_rate == Decimal("0.05")
    assert account.balance == Decimal("949.00")
    assert len(account.balance_history) == 3

    with pytest.raises(InvalidOperationError, match="below"):
        account.withdraw(Decimal("850.00"))


def test_day2_premium_has_increased_limit_fixed_fee_and_overdraft(
    client_factory,
):
    account = PremiumAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )
    account.deposit(Decimal("500"))
    account.withdraw(Decimal("700"))

    assert account.withdrawal_limit > BankAccount.WITHDRAWAL_LIMIT
    assert account.fixed_commission == Decimal("1")
    assert account.balance == Decimal("-201")

    with pytest.raises(InvalidOperationError, match="Withdrawal limit"):
        account.withdraw(Decimal("5001"))


def test_day2_premium_enforces_overdraft_limit(client_factory):
    account = PremiumAccount(
        client=client_factory(),
        currency=AccountCurrency.RUB,
    )

    with pytest.raises(InsufficientFundsError, match="overdraft"):
        account.withdraw(Decimal("1000"))


def test_day2_investment_portfolio_and_yearly_projection(client_factory):
    account = InvestmentAccount(
        client=client_factory(),
        currency=AccountCurrency.CNY,
    )
    account.deposit(Decimal("1000"))
    account.allocate_asset(InvestmentAccountActives.stocks, Decimal("400"))
    account.allocate_asset(InvestmentAccountActives.bonds, Decimal("250"))
    balance_before_projection = account.balance
    history_before_projection = account.balance_history

    projected_balance = account.project_yearly_growth()

    assert account.portfolio == {
        InvestmentAccountActives.stocks: Decimal("400"),
        InvestmentAccountActives.bonds: Decimal("250"),
        InvestmentAccountActives.etf: Decimal("0"),
    }
    assert projected_balance == Decimal("1130.00")
    assert account.balance == balance_before_projection
    assert account.balance_history == history_before_projection

    with pytest.raises(InsufficientFundsError, match="allocation"):
        account.allocate_asset(InvestmentAccountActives.etf, Decimal("1000"))


@pytest.mark.parametrize(
    "account_class",
    [SavingsAccount, PremiumAccount, InvestmentAccount],
)
def test_day2_special_accounts_override_polymorphic_methods(account_class):
    assert "withdraw" in account_class.__dict__
    assert "get_account_info" in account_class.__dict__
    assert "__str__" in account_class.__dict__
