from .models import (
    BankAccount,
    InvestmentAccount,
    PremiumAccount,
    SavingsAccount,
)

user_rub_account: BankAccount = BankAccount("Max Testov", "RUB", "active")

print('user_rub_account')
print(user_rub_account)
user_rub_account.deposit(100)
print(user_rub_account.get_account_info())
user_rub_account.withdraw(50)
print(user_rub_account.get_account_info())

investment_account: InvestmentAccount = InvestmentAccount(
    'Anna Testova', 'RUB', 'active')

print('investment_account')
print(investment_account)
investment_account.deposit(100)
print(investment_account.get_account_info())
investment_account.withdraw(50)
print(investment_account.get_account_info())

premium_account: PremiumAccount = PremiumAccount(
    'Oleg Testov', 'KZT', 'active')

print('investment_account')
print(premium_account)
premium_account.deposit(100)
print(premium_account.get_account_info())
premium_account.withdraw(50)
print(premium_account.get_account_info())

saving_account: SavingsAccount = SavingsAccount(
    'Bob Testov', 'USD', 'active')

print('investment_account')
print(saving_account)
saving_account.deposit(160)
print(saving_account.get_account_info())
saving_account.withdraw(50)
print(saving_account.get_account_info())
