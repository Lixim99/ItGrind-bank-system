from decimal import Decimal

import pytest

from src.bank import Bank
from src.enums import AccountCurrency, AccountStatus, ClientStatus
from src.exceptions import InvalidOperationError
from src.models import BankAccount, SavingsAccount


def test_client_validates_age_and_exposes_contacts(client_factory):
    with pytest.raises(ValueError):
        client_factory(age=17)

    client = client_factory(
        first_name=" Alice ",
        last_name=" Smith ",
        email="ALICE@EXAMPLE.COM",
    )

    assert client.first_name == "Alice"
    assert client.last_name == "Smith"
    assert client.email == "alice@example.com"
    assert client.contacts == {
        "email": "alice@example.com",
        "phone": client.phone,
    }
    assert client.account_numbers == []


def test_bank_rejects_duplicate_phone(client_factory):
    bank = Bank()
    client = client_factory(1)
    bank.add_client(client)

    with pytest.raises(ValueError):
        bank.add_client(client_factory(2, phone=client.phone))


def test_authentication_blocks_client_after_three_failures(client_factory):
    bank = Bank()
    client = client_factory()
    bank.add_client(client)

    for _ in range(bank.MAX_FAILED_LOGIN_ATTEMPTS):
        assert bank.authenticate_client(client.phone, "wrong-password") is None

    assert client.status is ClientStatus.BLOCKED
    assert client.is_blocked
    assert client.is_suspicious
    assert client.failed_login_attempts == 3
    assert bank.authenticate_client(client.phone, "secret-password") is None


def test_successful_authentication_resets_failure_counter(client_factory):
    bank = Bank()
    client = client_factory()
    bank.add_client(client)

    assert bank.authenticate_client(client.phone, "wrong-password") is None
    assert bank.authenticate_client(client.phone, "secret-password") is client
    assert client.failed_login_attempts == 0


def test_open_search_and_rank_accounts(client_factory):
    bank = Bank()
    first = client_factory(1)
    second = client_factory(2)
    bank.add_client(first)
    bank.add_client(second)

    first_rub = bank.open_account(
        client=first,
        account_class=BankAccount,
        currency=AccountCurrency.RUB,
    )
    second_rub = bank.open_account(
        client=second,
        account_class=BankAccount,
        currency=AccountCurrency.RUB,
    )
    savings = bank.open_account(
        client=second,
        account_class=SavingsAccount,
        currency=AccountCurrency.USD,
    )
    assert first_rub is not None
    assert second_rub is not None
    assert savings is not None

    first_rub.deposit(Decimal("100"))
    second_rub.deposit(Decimal("300"))

    assert first.account_numbers == [str(first_rub.id)]
    assert bank.search_accounts(
        currency=AccountCurrency.RUB,
        client=first,
    ) == [first_rub]
    assert bank.get_total_balance(AccountCurrency.RUB) == Decimal("400")
    assert bank.get_clients_ranking(AccountCurrency.RUB) == [second, first]


def test_bank_controls_account_status_transitions(client_factory):
    bank = Bank()
    client = client_factory()
    bank.add_client(client)
    account = bank.open_account(
        client=client,
        account_class=BankAccount,
        currency=AccountCurrency.RUB,
    )
    assert account is not None

    bank.freeze_account(account)
    assert account.status is AccountStatus.FROZEN
    with pytest.raises(InvalidOperationError):
        bank.freeze_account(account)

    bank.unfreeze_account(account)
    assert account.status is AccountStatus.ACTIVE
    bank.close_account(account)
    assert account.status is AccountStatus.CLOSED
    with pytest.raises(InvalidOperationError):
        bank.unfreeze_account(account)


def test_unknown_client_cannot_open_account(client_factory):
    bank = Bank()

    with pytest.raises(ValueError):
        bank.open_account(
            client=client_factory(),
            account_class=BankAccount,
            currency=AccountCurrency.RUB,
        )
