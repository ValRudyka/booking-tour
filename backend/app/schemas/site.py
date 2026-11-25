"""Public site information (no login)."""
from pydantic import BaseModel


class SiteContactsOut(BaseModel):
    """Support contacts from the global settings (form 4.6.4.1, fields 8–9, and the office address,
    spec 13 §3); null = not set."""
    phone: str | None
    email: str | None
    address: str | None = None
