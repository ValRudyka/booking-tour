"""Domain errors raised by services; routers turn them into HTTP responses."""


class DomainError(Exception):
    """Business-rule violation with a Ukrainian message for the client."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
