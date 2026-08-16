from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace

import pytest

from src import policy
from src.models import Client
from src.utils import BANK_TIMEZONE


@pytest.fixture(autouse=True)
def bank_clock(monkeypatch) -> SimpleNamespace:
    clock = SimpleNamespace(
        now=datetime(
            2026,
            1,
            1,
            12,
            tzinfo=BANK_TIMEZONE,
        )
    )
    monkeypatch.setattr(policy, "bank_now", lambda: clock.now)

    return clock


@pytest.fixture
def client_factory() -> Callable[..., Client]:
    """Create valid clients with unique contacts."""

    def make_client(number: int = 1, **overrides: object) -> Client:
        values = {
            "first_name": f"Client{number}",
            "last_name": "Test",
            "middle_name": "Middle",
            "phone": f"+70000000{number:03d}",
            "age": 30,
            "email": f"client{number}@example.com",
            "password": "secret-password",
        }
        values.update(overrides)
        return Client(**values)

    return make_client
