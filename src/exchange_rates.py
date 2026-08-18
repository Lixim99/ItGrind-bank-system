from decimal import Decimal
from typing import Final

from .enums import AccountCurrency

# Стоимость единицы валюты в базовой валюте банка (RUB).
RUB_RATES: Final[dict[AccountCurrency, Decimal]] = {
    AccountCurrency.RUB: Decimal("1.0"),
    AccountCurrency.USD: Decimal("82.1665"),
    AccountCurrency.EUR: Decimal("94.8366"),
    AccountCurrency.KZT: Decimal("0.175765"),
    AccountCurrency.CNY: Decimal("12.1655"),
}
