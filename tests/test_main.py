import unittest

from src.exceptions import AccountFrozenError
from src.models import BankAccount


class TestBankAccount(unittest.TestCase):
    def test_create_active_and_frozen_accounts(self):
        active_account = BankAccount("Max Testov", "RUB", "active")
        frozen_account = BankAccount("Anna Testova", "USD", "frozen")

        self.assertEqual(active_account.status, "active")
        self.assertEqual(active_account.balance, 0.0)
        self.assertEqual(frozen_account.status, "frozen")
        self.assertEqual(frozen_account.balance, 0.0)

    def test_frozen_account_rejects_deposit_and_withdrawal(self):
        frozen_account = BankAccount("Max Testov", "RUB", "frozen")

        with self.assertRaises(AccountFrozenError):
            frozen_account.deposit(100)

        with self.assertRaises(AccountFrozenError):
            frozen_account.withdraw(50)

        self.assertEqual(frozen_account.balance, 0.0)

    def test_valid_deposit_and_withdrawal(self):
        account = BankAccount("Max Testov", "RUB", "active")

        account.deposit(100)
        self.assertEqual(account.balance, 100.0)

        account.withdraw(40)
        self.assertEqual(account.balance, 60.0)
