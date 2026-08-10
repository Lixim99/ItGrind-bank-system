
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


class TransactionStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PROCESSING = "processing"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TransactionType(Enum):
    INNER = "inner"
    EXTERLAN = "external"


class TransactionPriority(Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 10
    CRITICAL = 100


class AuditLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RiskLevel(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
