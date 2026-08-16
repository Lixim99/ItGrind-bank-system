from decimal import Decimal
from types import MappingProxyType

import pytest

from src.bank import Bank
from src.enums import AccountCurrency, AccountStatus, ClientStatus
from src.exceptions import InvalidOperationError
from src.models import BankAccount, SavingsAccount


def test_day3_client_validates_identity_age_and_contacts(client_factory):
    with pytest.raises(ValueError, match="at least 18"):
        client_factory(age=17)

    client = client_factory(
        first_name=" Alice ",
        last_name=" Smith ",
        email=" ALICE@EXAMPLE.COM ",
        phone=" +79990000000 ",
    )

    assert client.first_name == "Alice"
    assert client.last_name == "Smith"
    assert client.email == "alice@example.com"
    assert client.contacts == {
        "email": "alice@example.com",
        "phone": "+79990000000",
    }
    assert client.status is ClientStatus.ACTIVE
    assert client.account_numbers == []


def test_day3_bank_rejects_duplicate_contacts_and_account_numbers(
    client_factory,
):
    bank = Bank()
    first = client_factory(1)
    second = client_factory(2)
    bank.add_client(first)
    bank.add_client(second)

    with pytest.raises(ValueError, match="phone"):
        bank.add_client(client_factory(3, phone=first.phone))

    bank.open_account(
        client=first,
        account_class=BankAccount,
        currency=AccountCurrency.RUB,
        account_number="DUPL1234",
    )

    with pytest.raises(ValueError, match="number"):
        bank.open_account(
            client=second,
            account_class=BankAccount,
            currency=AccountCurrency.RUB,
            account_number="DUPL1234",
        )


def test_day3_three_failed_logins_block_and_mark_client(client_factory):
    bank = Bank()
    client = bank.add_client(client_factory())

    for _ in range(bank.MAX_FAILED_LOGIN_ATTEMPTS):
        assert bank.authenticate_client(client.phone, "wrong") is None

    assert client.status is ClientStatus.BLOCKED
    assert client.failed_login_attempts == 3
    assert client.is_suspicious
    assert bank.authenticate_client(client.phone, "secret-password") is None


def test_day3_successful_login_resets_failed_attempts(client_factory):
    bank = Bank()
    client = bank.add_client(client_factory())

    assert bank.authenticate_client(client.phone, "wrong") is None
    assert bank.authenticate_client(client.phone, "secret-password") is client
    assert client.failed_login_attempts == 0


def test_day3_open_search_total_balance_and_ranking(client_factory):
    bank = Bank()
    first = bank.add_client(client_factory(1))
    second = bank.add_client(client_factory(2))
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
    bank.open_account(
        client=second,
        account_class=SavingsAccount,
        currency=AccountCurrency.USD,
    )
    first_rub.deposit(Decimal("100"))
    second_rub.deposit(Decimal("300"))

    assert first.account_numbers == [first_rub.account_number]
    assert bank.search_accounts(
        currency=AccountCurrency.RUB,
        client=first,
    ) == [first_rub]
    assert bank.get_total_balance(AccountCurrency.RUB) == Decimal("400")
    assert bank.get_clients_ranking(AccountCurrency.RUB) == [second, first]


def test_day3_bank_controls_valid_status_transitions(client_factory):
    bank = Bank()
    client = bank.add_client(client_factory())
    account = bank.open_account(
        client=client,
        account_class=BankAccount,
        currency=AccountCurrency.RUB,
    )

    bank.freeze_account(account)
    assert account.status is AccountStatus.FROZEN

    with pytest.raises(InvalidOperationError):
        bank.freeze_account(account)

    bank.unfreeze_account(account)
    bank.close_account(account)
    assert account.status is AccountStatus.CLOSED

    with pytest.raises(InvalidOperationError):
        bank.unfreeze_account(account)


def test_day3_night_policy_blocks_open_account(client_factory, bank_clock):
    bank = Bank()
    client = bank.add_client(client_factory())
    bank_clock.now = bank_clock.now.replace(hour=1)

    with pytest.raises(InvalidOperationError, match="00:00 to 05:00"):
        bank.open_account(
            client=client,
            account_class=BankAccount,
            currency=AccountCurrency.RUB,
        )

    assert not bank.accounts
    assert not client.accounts


@pytest.mark.parametrize(
    ("method_name", "initial_status"),
    [
        ("close_account", AccountStatus.ACTIVE),
        ("freeze_account", AccountStatus.ACTIVE),
        ("unfreeze_account", AccountStatus.FROZEN),
    ],
)
def test_day3_night_policy_blocks_account_status_operations(
    client_factory,
    bank_clock,
    method_name,
    initial_status,
):
    bank = Bank()
    client = bank.add_client(client_factory())
    account = bank.open_account(
        client=client,
        account_class=BankAccount,
        currency=AccountCurrency.RUB,
    )
    account.change_account_status(initial_status)
    bank_clock.now = bank_clock.now.replace(hour=1)

    with pytest.raises(InvalidOperationError, match="00:00 to 05:00"):
        getattr(bank, method_name)(account)

    assert account.status is initial_status


def test_day3_bank_rejects_unregistered_or_blocked_client(client_factory):
    bank = Bank()

    with pytest.raises(ValueError, match="not created"):
        bank.open_account(
            client=client_factory(),
            account_class=BankAccount,
            currency=AccountCurrency.RUB,
        )

    client = bank.add_client(client_factory(2))

    for _ in range(bank.MAX_FAILED_LOGIN_ATTEMPTS):
        bank.authenticate_client(client.phone, "wrong")

    with pytest.raises(InvalidOperationError, match="blocked"):
        bank.open_account(
            client=client,
            account_class=BankAccount,
            currency=AccountCurrency.RUB,
        )


def test_encapsulation_returns_read_only_collections(client_factory):
    bank = Bank()
    client = bank.add_client(client_factory())
    bank.open_account(
        client=client,
        account_class=BankAccount,
        currency=AccountCurrency.RUB,
    )

    assert isinstance(bank.clients, MappingProxyType)
    assert isinstance(bank.accounts, MappingProxyType)
    assert isinstance(client.accounts, tuple)

    with pytest.raises(TypeError):
        bank.clients[client.id] = client
