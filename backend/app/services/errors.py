"""Domain errors raised by services; routers turn them into HTTP responses."""


class DomainError(Exception):
    """Business-rule violation with a Ukrainian message for the client.

    `loc` (optional) names the request field the rule is about, in FastAPI's validation format,
    e.g. ("body", "tourists", 1, "passport_expiry"). Routers that support it (orders) answer like
    a FastAPI 422, {"detail": [{"loc", "msg", "type"}]}, so the frontend can show the message
    under that field; without `loc` the answer stays {"detail": "text"}.
    """

    def __init__(self, message: str, status_code: int = 400,
                 loc: tuple[str | int, ...] | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.loc = loc
