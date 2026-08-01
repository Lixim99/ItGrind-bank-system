class AccountFrozenError(Exception):
    def __init__(self):
        super().__init__("Frozen account error.")


class AccountClosedError(Exception):
    def __init__(self):
        super().__init__("Closed account error.")


class InvalidOperationError(Exception):
    def __init__(self, message: str):
        super().__init__(f"Invalid operation: {message}")


class InsufficientFundsError(Exception):
    def __init__(self):
        super().__init__("Insufficient funds error.")
