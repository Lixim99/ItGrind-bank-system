import unittest

from src.exceptions import (
    AccountFrozenError,
    InsufficientFundsError,
    InvalidOperationError,
)
from src.models import (
    BankAccount,
    InvestmentAccount,
    PremiumAccount,
    SavingsAccount,
)


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
        self.assertAlmostEqual(account.balance, 59.6)


class TestSavingsAccount(unittest.TestCase):
    def test_multiple_savings_accounts_operations(self):
        first_account = SavingsAccount("Max Testov", "RUB")
        second_account = SavingsAccount("Anna Testova", "USD")

        first_account.deposit(1000)
        second_account.deposit(200)

        first_account.apply_monthly_interest()
        second_account.withdraw(50)
        second_account.apply_monthly_interest()

        self.assertAlmostEqual(first_account.balance, 1050.0)
        self.assertAlmostEqual(second_account.balance, 156.975)
        self.assertEqual(
            first_account.get_account_info()["Monthly Interest Rate"],
            0.05,
        )

    def test_savings_account_minimum_balance_rules(self):
        account_without_minimum = SavingsAccount("Max Testov", "RUB")
        account_without_minimum.deposit(99)

        with self.assertRaises(InvalidOperationError):
            account_without_minimum.apply_monthly_interest()

        account_with_minimum = SavingsAccount("Anna Testova", "RUB")
        account_with_minimum.deposit(150)

        with self.assertRaises(InvalidOperationError):
            account_with_minimum.withdraw(50)

        self.assertEqual(account_with_minimum.balance, 150.0)


class TestPremiumAccount(unittest.TestCase):
    def test_multiple_premium_accounts_operations(self):
        account_with_large_withdrawal = PremiumAccount("Max Testov", "RUB")
        account_with_overdraft = PremiumAccount("Anna Testova", "USD")

        account_with_large_withdrawal.deposit(3000)
        account_with_large_withdrawal.withdraw(1500)

        account_with_overdraft.deposit(500)
        account_with_overdraft.withdraw(1000)

        self.assertAlmostEqual(account_with_large_withdrawal.balance, 1499.0)
        self.assertAlmostEqual(account_with_overdraft.balance, -501.0)
        self.assertEqual(
            account_with_overdraft.get_account_info()["Fixed Commission"],
            1,
        )

    def test_premium_account_limits(self):
        account_over_withdrawal_limit = PremiumAccount("Max Testov", "RUB")
        account_over_withdrawal_limit.deposit(10_000)

        with self.assertRaises(InvalidOperationError):
            account_over_withdrawal_limit.withdraw(5000)

        account_over_overdraft_limit = PremiumAccount("Anna Testova", "RUB")

        with self.assertRaises(InsufficientFundsError):
            account_over_overdraft_limit.withdraw(1000)


class TestInvestmentAccount(unittest.TestCase):
    def test_multiple_investment_accounts_operations(self):
        first_account = InvestmentAccount("Max Testov", "RUB")
        second_account = InvestmentAccount("Anna Testova", "EUR")

        first_account.deposit(1000)
        second_account.deposit(2000)

        first_account.project_yearly_growth()
        second_account.project_yearly_growth()
        first_account.withdraw(100)

        self.assertAlmostEqual(first_account.balance, 1029.0)
        self.assertAlmostEqual(second_account.balance, 2260.0)
        self.assertEqual(
            second_account.get_account_info()["ACTIVES"],
            ["stocks", "bonds", "etf"],
        )

    def test_investment_growth_requires_positive_balance(self):
        first_account = InvestmentAccount("Max Testov", "RUB")
        second_account = InvestmentAccount("Anna Testova", "CNY")

        with self.assertRaises(InvalidOperationError):
            first_account.project_yearly_growth()

        with self.assertRaises(InvalidOperationError):
            second_account.project_yearly_growth()
