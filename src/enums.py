
from enum import Enum


class Currency(Enum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"
    KZT = "KZT"
    CNY = "CNY"


class AccountStatus(Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    FROZEN = "frozen"
