"""System administrator: reference data (ТЗ 4.3 «ведення довідників … архівування неактуальних
записів», use case «Архівувати застарілі записи довідників»).

- Archive / restore instead of deleting: an archived item disappears from the public lists and
  cannot be chosen for new tours or orders, but stays on the existing ones. Archiving a country
  also hides its resorts, hotels and cities from the public lists.
- Archiving is refused while a published tour (status active) uses the item: its hotel, the
  hotel's resort or country, or its departure city (spec 13 §2). The catalog does not look at
  is_archived, so the tour would stay for sale; unpublish it first. Drafts do not block it
  (publishing re-checks the hotel and city, services/tours.py).
- Every refusal is a function (archive_refusal, restore_refusal, default_refusal,
  delete_refusal, language_*_refusal): the endpoints raise it, services/admin_actions.py returns
  it as the reason of a disabled button.
- DELETE removes only items nothing refers to (no tour, order, review, user, child item); the
  references are found from the foreign keys in the models, so a new table is covered too.
- Exactly one default insurance type and one default transfer type: making an item the default
  unsets the old one in the same transaction; the default cannot be un-defaulted, archived or
  deleted (choose another default first). The database allows at most one (partial unique index).
- hotels.rating_avg is read-only (it comes from published reviews).
Every change is written to the audit log.
"""
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Base, City, Country, Hotel, InsuranceType, Language, Resort, Tour, TransferType, User
from app.models.enums import TourStatus
from app.services.audit import audit, changed, snapshot
from app.services.errors import DomainError
from app.services.text_lists import clean_text_list


@dataclass(frozen=True)
class Kind:
    model: type
    entity: str          # audit_log.entity
    label: str           # Ukrainian, for messages
    fields: tuple[str, ...]
    order_by: str


KINDS: dict[str, Kind] = {
    "countries": Kind(Country, "country", "Країна", ("iso_code", "name_uk", "name_en", "is_archived"), "name_uk"),
    "cities": Kind(City, "city", "Місто", ("country_id", "name_uk", "name_en", "iata_code", "is_archived"), "name_uk"),
    "resorts": Kind(Resort, "resort", "Курорт", ("country_id", "name_uk", "name_en", "is_archived"), "name_uk"),
    "hotels": Kind(Hotel, "hotel", "Готель", ("resort_id", "name", "stars", "description", "beach_line",
                                              "distance_to_beach_m", "distance_to_airport_km", "check_in",
                                              "check_out", "amenities", "room_types", "is_archived"), "name"),
    "insurance-types": Kind(InsuranceType, "insurance_type", "Тип страхування",
                            ("name_uk", "price_uah", "is_default", "is_archived"), "price_uah"),
    "transfer-types": Kind(TransferType, "transfer_type", "Тип трансферу",
                           ("name_uk", "price_uah", "is_default", "is_archived"), "price_uah"),
}
DEFAULT_KINDS = ("insurance-types", "transfer-types")
ISO_RE, IATA_RE, LANG_RE = re.compile(r"^[A-Z]{2}$"), re.compile(r"^[A-Z]{3}$"), re.compile(r"^[a-z]{2,5}$")


def _kind(kind: str) -> Kind:
    return KINDS[kind]


def list_items(db: Session, kind: str, archived: bool | None, parent_id: int | None) -> list[Any]:
    spec = _kind(kind)
    query = select(spec.model)
    if archived is not None:
        query = query.where(spec.model.is_archived.is_(archived))
    if parent_id is not None:
        parent = "resort_id" if kind == "hotels" else "country_id"
        if hasattr(spec.model, parent):
            query = query.where(getattr(spec.model, parent) == parent_id)
    return list(db.scalars(query.order_by(getattr(spec.model, spec.order_by), spec.model.id)))


def get_item(db: Session, kind: str, item_id: int, lock: bool = False):
    spec = _kind(kind)
    query = select(spec.model).where(spec.model.id == item_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(query)
    if item is None:
        raise DomainError(f"{spec.label}: запис не знайдено", 404)
    return item


# ---------- validation
def _text(value: Any, label: str, required: bool, limit: int) -> str | None:
    value = (value or "").strip() or None
    if required and value is None:
        raise DomainError(f"Вкажіть «{label}»", 422)
    if value and len(value) > limit:
        raise DomainError(f"«{label}» — не довше {limit} символів", 422)
    return value


PARENT_TEXT = {Country: ("Країну не знайдено", "Країна архівна — спершу відновіть її"),
               Resort: ("Курорт не знайдено", "Курорт архівний — спершу відновіть його")}


def _parent(db: Session, model: type, parent_id: Any) -> None:
    missing, archived = PARENT_TEXT[model]
    parent = db.get(model, parent_id) if parent_id is not None else None
    if parent is None:
        raise DomainError(missing, 422)
    if parent.is_archived:
        raise DomainError(archived, 409)


MAX_DISTANCE_TO_BEACH_M = 50_000
MAX_DISTANCE_TO_AIRPORT_KM = 1_000


def _whole_number(value: Any, label: str, low: int, high: int) -> int | None:
    if value is None:
        return None
    if not low <= value <= high:
        raise DomainError(f"«{label}» — від {low} до {high}", 422)
    return value


def _hotel_facts(data: dict[str, Any], has) -> dict[str, Any]:
    """Hotel facts for the tour page (form 4.6.4.2). Pydantic has already checked the types
    (whole numbers, HH:MM times, lists of strings)."""
    out: dict[str, Any] = {}
    if has("beach_line"):
        out["beach_line"] = _whole_number(data.get("beach_line"), "Лінія пляжу", 1, 5)
    if has("distance_to_beach_m"):
        out["distance_to_beach_m"] = _whole_number(data.get("distance_to_beach_m"),
                                                   "Відстань до пляжу, м", 0, MAX_DISTANCE_TO_BEACH_M)
    if has("distance_to_airport_km"):
        out["distance_to_airport_km"] = _whole_number(data.get("distance_to_airport_km"),
                                                      "Відстань до аеропорту, км", 0,
                                                      MAX_DISTANCE_TO_AIRPORT_KM)
    for field in ("check_in", "check_out"):
        if has(field):
            out[field] = data.get(field)
    if has("amenities"):
        out["amenities"] = clean_text_list(data.get("amenities"), "Зручності")
    if has("room_types"):
        out["room_types"] = clean_text_list(data.get("room_types"), "Типи номерів")
    return out


def _clean(db: Session, kind: str, data: dict[str, Any], item=None) -> dict[str, Any]:
    """Validated values for the fields that were sent (create: all required ones)."""
    creating = item is None
    out: dict[str, Any] = {}

    def has(field: str) -> bool:
        return field in data

    if kind == "countries":
        if creating or has("iso_code"):
            code = (data.get("iso_code") or "").strip().upper()
            if not ISO_RE.match(code):
                raise DomainError("Код країни — 2 латинські літери (ISO 3166-1), наприклад UA", 422)
            clash = db.scalar(select(Country.id).where(Country.iso_code == code))
            if clash is not None and (creating or clash != item.id):
                raise DomainError(f"Країна з кодом {code} вже є", 409)
            out["iso_code"] = code
    if kind in ("cities", "resorts") and (creating or has("country_id")):
        _parent(db, Country, data.get("country_id"))
        out["country_id"] = data["country_id"]
    if kind == "hotels" and (creating or has("resort_id")):
        _parent(db, Resort, data.get("resort_id"))
        out["resort_id"] = data["resort_id"]
    if kind == "cities" and has("iata_code"):
        code = (data.get("iata_code") or "").strip().upper() or None
        if code is not None and not IATA_RE.match(code):
            raise DomainError("Код аеропорту IATA — 3 латинські літери, наприклад KBP", 422)
        out["iata_code"] = code
    if kind in ("countries", "cities", "resorts", "insurance-types", "transfer-types"):
        if creating or has("name_uk"):
            out["name_uk"] = _text(data.get("name_uk"), "Назва українською", True, 100)
    if kind in ("countries", "cities", "resorts") and has("name_en"):
        out["name_en"] = _text(data.get("name_en"), "Назва англійською", False, 100)
    if kind == "hotels":
        if creating or has("name"):
            out["name"] = _text(data.get("name"), "Назва готелю", True, 150)
        if has("stars"):
            stars = data.get("stars")
            if stars is not None and not 1 <= stars <= 5:
                raise DomainError("Зірковість готелю — від 1 до 5", 422)
            out["stars"] = stars
        if has("description"):
            out["description"] = _text(data.get("description"), "Опис", False, 5000)
        out.update(_hotel_facts(data, has))
    if kind in DEFAULT_KINDS and (creating or has("price_uah")):
        price = data.get("price_uah")
        if price is None or Decimal(price) < 0 or Decimal(price) > Decimal("1000000"):
            raise DomainError("Ціна — від 0 до 1 000 000 грн", 422)
        out["price_uah"] = Decimal(price).quantize(Decimal("0.01"))
    return out


# ---------- create / update / archive / delete
def _make_default(db: Session, kind: str, item) -> None:
    """The new default replaces the old one in the same transaction."""
    model = _kind(kind).model
    db.execute(update(model).where(model.id != item.id, model.is_default.is_(True)).values(is_default=False))
    db.flush()
    item.is_default = True


def create_item(db: Session, admin: User, kind: str, data: dict[str, Any]):
    spec = _kind(kind)
    values = _clean(db, kind, data)
    item = spec.model(**values)
    db.add(item)
    db.flush()
    if kind in DEFAULT_KINDS and data.get("is_default"):
        _make_default(db, kind, item)
        db.flush()
    audit(db, admin, spec.entity, item.id, "created", new=snapshot(item, spec.fields))
    return item


def update_item(db: Session, admin: User, kind: str, item_id: int, data: dict[str, Any]):
    spec = _kind(kind)
    item = get_item(db, kind, item_id, lock=True)
    before = snapshot(item, spec.fields)
    values = _clean(db, kind, data, item)
    if kind in DEFAULT_KINDS and "is_default" in data and data["is_default"] is not None:
        if data["is_default"] and not item.is_default:
            if reason := default_refusal(item):
                raise DomainError(reason, 409)
            _make_default(db, kind, item)
        elif not data["is_default"] and item.is_default:
            raise DomainError("Має бути один тип за замовчуванням — призначте типовим інший запис", 409)
    for field, value in values.items():
        setattr(item, field, value)
    db.flush()
    old, new = changed(before, snapshot(item, spec.fields))
    if new:
        audit(db, admin, spec.entity, item.id, "updated", old, new)
    return item


def set_archived(db: Session, admin: User, kind: str, item_id: int, archived: bool):
    spec = _kind(kind)
    item = get_item(db, kind, item_id, lock=True)
    if item.is_archived == archived:
        return item
    context = refusal_context(db, kind, [item])
    reason = (archive_refusal(kind, item, context) if archived
              else restore_refusal(kind, item, context))
    if reason:
        raise DomainError(reason, 409)
    item.is_archived = archived
    db.flush()
    audit(db, admin, spec.entity, item.id, "archived" if archived else "restored",
          {"is_archived": not archived}, {"is_archived": archived})
    return item


# ---------- refusals
# Rows that refer to an item, by "table.column", in Ukrainian for the delete refusal.
REFERENCE_LABELS = {
    "cities.country_id": "міста вильоту", "resorts.country_id": "курорти",
    "users.citizenship_id": "користувачі (громадянство)", "tours.departure_city_id": "тури",
    "hotels.resort_id": "готелі", "tours.hotel_id": "тури", "reviews.hotel_id": "відгуки",
    "orders.insurance_type_id": "замовлення", "orders.transfer_type_id": "замовлення",
}
PARENT_COLUMN = {"cities": "country_id", "resorts": "country_id", "hotels": "resort_id"}


def _published_tours(db: Session, kind: str, ids: list[int]) -> dict[int, int]:
    """{item id: published tours that use it} for hotels, resorts, countries and cities."""
    active = Tour.status == TourStatus.ACTIVE
    queries = []
    if kind == "hotels":
        queries.append(select(Tour.hotel_id, Tour.id).where(active, Tour.hotel_id.in_(ids)))
    elif kind == "resorts":
        queries.append(select(Hotel.resort_id, Tour.id).join(Hotel, Tour.hotel_id == Hotel.id)
                       .where(active, Hotel.resort_id.in_(ids)))
    elif kind == "countries":
        queries.append(select(Resort.country_id, Tour.id).join(Hotel, Tour.hotel_id == Hotel.id)
                       .join(Resort, Hotel.resort_id == Resort.id).where(active, Resort.country_id.in_(ids)))
        queries.append(select(City.country_id, Tour.id).join(City, Tour.departure_city_id == City.id)
                       .where(active, City.country_id.in_(ids)))
    elif kind == "cities":
        queries.append(select(Tour.departure_city_id, Tour.id).where(active, Tour.departure_city_id.in_(ids)))
    tours: dict[int, set[int]] = {}
    for query in queries:
        for item_id, tour_id in db.execute(query):
            tours.setdefault(item_id, set()).add(tour_id)
    return {item_id: len(found) for item_id, found in tours.items()}


def _references(db: Session, table: str, ids: list[Any]) -> dict[Any, dict[str, int]]:
    """{item id: {"tours.hotel_id": 3, ...}}: rows of other tables that point at each item, one
    grouped count per foreign key (found from the models, so a new table is covered too)."""
    found: dict[Any, dict[str, int]] = {}
    for other in Base.metadata.sorted_tables:
        for fk in other.foreign_keys:
            if fk.column.table.name == table:
                query = (select(fk.parent, func.count()).select_from(other)
                         .where(fk.parent.in_(ids)).group_by(fk.parent))
                for item_id, count in db.execute(query):
                    found.setdefault(item_id, {})[f"{other.name}.{fk.parent.name}"] = count
    return found


def references(db: Session, table: str, item_id: Any) -> dict[str, int]:
    """{"tours.hotel_id": 3, ...} for one item."""
    return _references(db, table, [item_id]).get(item_id, {})


def refusal_context(db: Session, kind: str, items: list[Any]) -> dict[str, Any]:
    """What the refusals of a list need, read in a few grouped queries (no query per row)."""
    ids = [item.id for item in items]
    context: dict[str, Any] = {"published": {}, "references": {}, "archived_parents": set()}
    if not ids:
        return context
    context["published"] = _published_tours(db, kind, ids)
    context["references"] = _references(db, _kind(kind).model.__tablename__, ids)
    column = PARENT_COLUMN.get(kind)
    if column:
        parent = Resort if kind == "hotels" else Country
        parent_ids = {getattr(item, column) for item in items}
        context["archived_parents"] = set(db.scalars(select(parent.id).where(
            parent.id.in_(parent_ids), parent.is_archived.is_(True))))
    return context


def archive_refusal(kind: str, item, context: dict[str, Any]) -> str | None:
    if getattr(item, "is_default", False):
        return "Типовий запис не архівується — спершу призначте типовим інший"
    count = context["published"].get(item.id, 0)
    if count == 1:
        return "Використовується в 1 опублікованому турі — спершу зніміть його з продажу"
    if count:
        return f"Використовується в опублікованих турах ({count}) — спершу зніміть їх з продажу"
    return None


def restore_refusal(kind: str, item, context: dict[str, Any]) -> str | None:
    """A child cannot come back under an archived parent."""
    column = PARENT_COLUMN.get(kind)
    if column and getattr(item, column) in context["archived_parents"]:
        return PARENT_TEXT[Resort if kind == "hotels" else Country][1]
    return None


def default_refusal(item) -> str | None:
    if item.is_archived:
        return "Архівний запис не може бути типовим"
    return None


def delete_refusal(kind: str, item, context: dict[str, Any]) -> str | None:
    if getattr(item, "is_default", False):
        return "Типовий запис не видаляється — спершу призначте типовим інший"
    used = context["references"].get(item.id)
    if not used:
        return None
    totals: dict[str, int] = {}
    for name, count in used.items():
        label = REFERENCE_LABELS.get(name, name)
        totals[label] = totals.get(label, 0) + count
    where = ", ".join(f"{label}: {count}" for label, count in totals.items())
    return f"{_kind(kind).label} використовується ({where}) — архівуйте замість видалення"


def delete_item(db: Session, admin: User, kind: str, item_id: int) -> None:
    spec = _kind(kind)
    item = get_item(db, kind, item_id, lock=True)
    if reason := delete_refusal(kind, item, refusal_context(db, kind, [item])):
        raise DomainError(reason, 409)
    old = snapshot(item, spec.fields)
    db.delete(item)
    db.flush()
    audit(db, admin, spec.entity, item_id, "deleted", old=old)


# ---------- languages (form 4.6.4.1, field 5): code is the key; no archive, only is_enabled
BASE_LANGUAGE = "uk"


def language_disable_refusal(language: Language) -> str | None:
    if language.code == BASE_LANGUAGE:
        return "Українська — основна мова сайту, її не можна вимкнути"
    return None


def language_delete_refusal(language: Language) -> str | None:
    if language.code == BASE_LANGUAGE:
        return "Українська — основна мова сайту, її не можна видалити"
    return None


def list_languages(db: Session) -> list[Language]:
    return list(db.scalars(select(Language).order_by(Language.code)))


def get_language(db: Session, code: str) -> Language:
    language = db.get(Language, code)
    if language is None:
        raise DomainError("Мову не знайдено", 404)
    return language


def create_language(db: Session, admin: User, code: str, name: str, is_enabled: bool) -> Language:
    code = (code or "").strip().lower()
    if not LANG_RE.match(code):
        raise DomainError("Код мови — 2–5 латинських літер, наприклад uk, en", 422)
    if db.get(Language, code) is not None:
        raise DomainError(f"Мова {code} вже є", 409)
    language = Language(code=code, name=_text(name, "Назва", True, 50), is_enabled=is_enabled)
    db.add(language)
    db.flush()
    audit(db, admin, "language", code, "created", new=snapshot(language, ("name", "is_enabled")))
    return language


def update_language(db: Session, admin: User, code: str, changes: dict[str, Any]) -> Language:
    language = get_language(db, code)
    before = snapshot(language, ("name", "is_enabled"))
    if changes.get("name") is not None:
        language.name = _text(changes["name"], "Назва", True, 50)
    if changes.get("is_enabled") is not None:
        if not changes["is_enabled"] and (reason := language_disable_refusal(language)):
            raise DomainError(reason, 409)
        language.is_enabled = changes["is_enabled"]
    db.flush()
    old, new = changed(before, snapshot(language, ("name", "is_enabled")))
    if new:
        audit(db, admin, "language", code, "updated", old, new)
    return language


def delete_language(db: Session, admin: User, code: str) -> None:
    language = get_language(db, code)
    if reason := language_delete_refusal(language):
        raise DomainError(reason, 409)
    old = snapshot(language, ("name", "is_enabled"))
    db.delete(language)
    db.flush()
    audit(db, admin, "language", code, "deleted", old=old)
