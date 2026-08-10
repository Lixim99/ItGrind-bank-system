
from enum import Enum


class AccountCurrency(Enum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"
    KZT = "KZT"
    CNY = "CNY"


class AccountStatus(Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    FROZEN = "frozen"


class ClientStatus(Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class InvestmentAccountActives(Enum):
    stocks = "stocks"
    bonds = "bonds"
    etf = "etf"
