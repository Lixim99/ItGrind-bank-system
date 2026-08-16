from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID

from .enums import (
    AccountCurrency,
    AccountStatus,
)
from .exceptions import InvalidOperationError
from .models import BankAccount, Client
from .policy import OperationPolicy
from .utils import password_hasher


class Bank:
    MAX_FAILED_LOGIN_ATTEMPTS: int = 3

    @property
    def clients(self) -> Mapping[UUID, Client]:
        return MappingProxyType(self._clients)

    @property
    def accounts(self) -> Mapping[UUID, BankAccount]:
        return MappingProxyType(self._accounts)

    def __init__(self) -> None:
        self._clients: dict[UUID, Client] = {}
        self._clients_by_phone: dict[str, UUID] = {}
        self._accounts: dict[UUID, BankAccount] = {}
        self._accounts_by_number: dict[str, UUID] = {}
        self._accounts_by_currency: dict[AccountCurrency, set[UUID]] = {}

    def add_client(self, client: Client) -> Client:
        if not isinstance(client, Client):
            raise TypeError("client must be a Client instance")

        old_client = self._get_client_by_phone(client.phone)

        if old_client is not None:
            raise ValueError("A client with this phone already exists")

        self._clients[client.id] = client
        self._clients_by_phone[client.phone] = client.id

        return client

    def authenticate_client(self, phone: str, password: str) -> Client | None:
        client = self._get_client_by_phone(phone)

        if client is None:
            return None

        if client.is_blocked:
            return None

        is_password_correct = password_hasher.verify(
            password,
            client.password_hash,
        )

        if not is_password_correct:
            client.register_failed_login(self.MAX_FAILED_LOGIN_ATTEMPTS)
            return None

        client.reset_failed_logins()

        return client

    def open_account(
        self,
        *,
        client: Client,
        account_class: type[BankAccount],
        currency: AccountCurrency,
        account_number: str | None = None,
    ) -> BankAccount:
        client = self._clients.get(client.id)

        if client is None:
            raise ValueError("Client is not created")

        self._ensure_client_can_transact(client)

        if not isinstance(account_class, type) or not issubclass(
            account_class,
            BankAccount,
        ):
            raise TypeError("account_class must inherit BankAccount")

        account = account_class(
            client=client,
            currency=currency,
            account_number=account_number,
        )

        if account.account_number in self._accounts_by_number:
            raise ValueError("An account with this number already exists")

        client.add_account(account)
        self._accounts[account.id] = account
        self._accounts_by_number[account.account_number] = account.id
        self._accounts_by_currency.setdefault(
            account.currency,
            set(),
        ).add(account.id)

        return account

    def close_account(self, account: BankAccount) -> None:
        account = self._accounts.get(account.id)

        if account is None:
            raise ValueError("Account not exist")

        self._ensure_client_can_transact(account.client)

        if account.status == AccountStatus.CLOSED:
            raise InvalidOperationError("Account is already closed")

        account.change_account_status(AccountStatus.CLOSED)

    def search_accounts(
        self,
        *,
        currency: AccountCurrency | None = None,
        client: Client | None = None,
    ) -> list[BankAccount]:
        if currency is not None:
            account_ids = self._accounts_by_currency.get(
                currency,
                set(),
            )

            accounts = [
                self._accounts[account_id]
                for account_id in account_ids
            ]
        else:
            accounts = list(self._accounts.values())

        if client is not None:
            accounts = [
                account
                for account in accounts
                if account.client.id == client.id
            ]

        return accounts

    def freeze_account(self, account: BankAccount) -> None:
        account = self._accounts.get(account.id)

        if account is None:
            raise ValueError("Account not exist")

        self._ensure_client_can_transact(account.client)

        if account.status != AccountStatus.ACTIVE:
            raise InvalidOperationError(
                "Only an active account can be frozen"
            )

        account.change_account_status(AccountStatus.FROZEN)

    def unfreeze_account(self, account: BankAccount) -> None:
        account = self._accounts.get(account.id)

        if account is None:
            raise ValueError("Account not exist")

        self._ensure_client_can_transact(account.client)

        if account.status != AccountStatus.FROZEN:
            raise InvalidOperationError(
                "Only a frozen account can be unfrozen.")

        account.change_account_status(AccountStatus.ACTIVE)

    def get_total_balance(
        self,
        currency: AccountCurrency,
        client: Client | None = None
    ) -> Decimal:
        accounts = self.search_accounts(client=client, currency=currency)

        return sum(
            (account.balance for account in accounts),
            start=Decimal(0),
        )

    def get_clients_ranking(self, currency: AccountCurrency) -> list[Client]:
        return sorted(
            self._clients.values(),
            key=lambda client: self.get_total_balance(currency, client),
            reverse=True,
        )

    def _get_client_by_phone(self, phone: str) -> Client | None:
        client_id = self._clients_by_phone.get(phone)

        if client_id is None:
            return None

        return self._clients.get(client_id)

    @staticmethod
    def _ensure_client_can_transact(client: Client | None) -> None:
        OperationPolicy.ensure_operation_allowed()

        if client is None:
            raise InvalidOperationError("Account has no registered client")
        if client.is_blocked:
            raise InvalidOperationError(
                "A blocked client cannot perform financial operations"
            )
