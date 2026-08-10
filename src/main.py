from decimal import Decimal

from .base import Base
from .database import SessionFactory, engine
from .enums import AccountCurrency
from .exceptions import AccountFrozenError
from .models import Bank, BankAccount, Client, SavingsAccount


def main() -> None:
    # Только для демонстрации: при каждом запуске данные создаются заново.
    # В рабочем проекте вместо drop_all/create_all используйте Alembic.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    first_client = Client.create(
        first_name="Максим",
        last_name="Литвинов",
        middle_name="Александрович",
        email="max@example.com",
        password="test-password",
        phone="79997202343",
        age=34
    )

    second_client = Client.create(
        first_name="Иван",
        last_name="Иванов",
        middle_name="Иванович",
        email="ivan@example.com",
        password="test-password",
        phone="79997202342",
        age=18
    )

    with SessionFactory.begin() as session:
        bank = Bank(session)

        # Регистрация клиентов.
        bank.add_client(first_client)
        bank.add_client(second_client)
        print("Клиенты:", first_client.full_name, "и", second_client.full_name)

        # Аутентификация: неудачная попытка, затем успешная.
        failed_auth = bank.authenticate_client(
            first_client.phone,
            "wrong-password",
        )
        successful_auth = bank.authenticate_client(
            first_client.phone,
            "test-password",
        )
        print("Вход с неверным паролем:", failed_auth)
        if successful_auth is None:
            raise RuntimeError(
                "Не удалось аутентифицировать тестового клиента")
        print("Успешный вход:", successful_auth.full_name)

        # Открытие обычного и накопительного счетов.
        rub_account = bank.open_account(BankAccount(
            client=first_client,
            currency=AccountCurrency.RUB,
        ))
        usd_savings = bank.open_account(SavingsAccount(
            client=second_client,
            currency=AccountCurrency.USD,
        ))

        # Финансовые операции используют Decimal.
        rub_account.deposit(Decimal("1000.00"))
        rub_account.withdraw(Decimal("250.00"))
        bank.save_account_transact(rub_account)

        usd_savings.deposit(Decimal("500.00"))
        usd_savings.apply_monthly_interest()
        bank.save_account_transact(usd_savings)

        print("Баланс RUB-счёта:", rub_account.balance)
        print("Баланс накопительного USD-счёта:", usd_savings.balance)

        # Замороженный счёт не принимает финансовые операции.
        bank.freeze_account(rub_account)
        try:
            rub_account.deposit(Decimal("100.00"))
        except AccountFrozenError as error:
            print("Операция по замороженному счёту отклонена:", error)

        bank.unfreeze_account(rub_account)
        rub_account.deposit(Decimal("100.00"))
        bank.save_account_transact(rub_account)

        # Поиск счетов и агрегаты банка.
        rub_accounts = bank.search_accounts(currency=AccountCurrency.RUB)
        print("Количество RUB-счетов:", len(rub_accounts))
        print(
            "Общий баланс в RUB:",
            bank.get_total_balance(AccountCurrency.RUB),
        )

        ranking = bank.get_clients_ranking(AccountCurrency.RUB)
        print("Рейтинг клиентов по RUB:")
        for position, client in enumerate(ranking, start=1):
            balance = bank.get_total_balance(AccountCurrency.RUB, client)
            print(f"{position}. {client.full_name}: {balance} RUB")

        # Закрытие счёта.
        bank.close_account(rub_account)
        print("Статус закрытого счёта:", rub_account.status.value)


if __name__ == "__main__":
    main()
