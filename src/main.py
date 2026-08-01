from .models import BankAccount

user_rub_account: BankAccount = BankAccount("Max Testov", "RUB", "active")

print(user_rub_account)
user_rub_account.deposit(100)
print(user_rub_account.get_account_info())
user_rub_account.withdraw(50)
print(user_rub_account.get_account_info())
