"""Short text lists stored as TEXT[]: «Що включено» / «Що не включено» of a tour, a hotel's
amenities and room types. One rule for all of them, so the forms behave the same."""
from collections.abc import Iterable

from app.services.errors import DomainError

MAX_ITEMS = 20
MAX_ITEM_LENGTH = 200


def clean_text_list(values: Iterable[str] | None, label: str) -> list[str]:
    """Trim every line, drop empty ones and exact repeats (order kept); limit count and length.
    `label` names the field in the Ukrainian error message."""
    cleaned: list[str] = []
    for value in values or []:
        text = " ".join(str(value).split())
        if not text or text in cleaned:
            continue
        if len(text) > MAX_ITEM_LENGTH:
            raise DomainError(f"{label}: кожен пункт — не довше {MAX_ITEM_LENGTH} символів", 422)
        cleaned.append(text)
    if len(cleaned) > MAX_ITEMS:
        raise DomainError(f"{label}: не більше {MAX_ITEMS} пунктів", 422)
    return cleaned
