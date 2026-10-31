"""Errors raised by the service."""


class SecretExists(Exception):
    """Raised when a secret name is already stored."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)
