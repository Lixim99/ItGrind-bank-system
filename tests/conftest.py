from collections.abc import Callable
from datetime import datetime

import pytest

from src.models import Client
from src.transaction import OperationPolicy
from src.utils import BANK_TIMEZONE


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


@pytest.fixture
def allowed_operation_policy() -> OperationPolicy:
    return OperationPolicy(
        clock=lambda: datetime(
            2026,
            1,
            1,
            12,
            tzinfo=BANK_TIMEZONE,
        )
    )


@pytest.fixture
def night_operation_policy() -> OperationPolicy:
    return OperationPolicy(
        clock=lambda: datetime(
            2026,
            1,
            1,
            1,
            tzinfo=BANK_TIMEZONE,
        )
    )
