"""Registration, login, profile and role checks."""
from datetime import timedelta

import pytest
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import require_roles
from app.core.security import create_access_token
from app.main import app
from app.models import Country, User
from app.models.enums import UserRole
from app.services.users import create_user

PASSWORD = "Strong-pass-123"


UA_ID: int | None = None


@pytest.fixture(autouse=True)
def _ukraine(db):
    """register_payload() needs the id of Ukraine (citizenship is required at registration)."""
    global UA_ID
    UA_ID = db.scalar(select(Country.id).where(Country.iso_code == "UA"))


def register_payload(**overrides):
    data = {"phone": "+380 50 123 45 67", "email": "Taras@Example.com", "password": PASSWORD,
            "last_name": "Шевченко", "first_name": "Тарас", "consent": True,
            "birth_date": "1990-05-14", "citizenship_id": UA_ID}
    data.update(overrides)
    return data


def login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", data={"username": username, "password": password})


def auth_header(client, username="+380501234567"):
    token = login(client, username).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def country_id(db, iso):
    return db.scalar(select(Country.id).where(Country.iso_code == iso))


# ---------- registration
def test_register_creates_client_with_hashed_password(client, db):
    response = client.post("/api/auth/register", json=register_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["phone"] == "+380501234567"        # spaces removed
    assert body["email"] == "taras@example.com"    # lower-cased
    assert body["role"] == "client"
    assert "password" not in body and "password_hash" not in body
    user = db.get(User, body["id"])
    assert user.password_hash.startswith("$argon2id$")
    assert user.consent_at is not None


def test_register_requires_consent(client):
    response = client.post("/api/auth/register", json=register_payload(consent=False))
    assert response.status_code == 422


@pytest.mark.parametrize("field,value", [
    ("phone", "0501234567"), ("email", "not-an-email"), ("password", "short"),
])
def test_register_validates_fields(client, field, value):
    assert client.post("/api/auth/register", json=register_payload(**{field: value})).status_code == 422


def test_register_duplicate_phone_and_email(client):
    assert client.post("/api/auth/register", json=register_payload()).status_code == 201
    dup_phone = client.post("/api/auth/register", json=register_payload(email="other@example.com"))
    assert dup_phone.status_code == 409
    dup_email = client.post("/api/auth/register", json=register_payload(phone="+380509999999"))
    assert dup_email.status_code == 409


def test_register_cannot_choose_role(client):
    response = client.post("/api/auth/register", json=register_payload(role="admin"))
    assert response.status_code == 201
    assert response.json()["role"] == "client"     # extra field ignored


def test_ukrainian_citizen_names_in_ukrainian(client, db):
    ua = country_id(db, "UA")
    latin = client.post("/api/auth/register", json=register_payload(
        citizenship_id=ua, last_name="Shevchenko", first_name="Taras"))
    assert latin.status_code == 422
    ok = client.post("/api/auth/register", json=register_payload(
        citizenship_id=ua, last_name="Стефанишин-Об'єдко", first_name="Ївга"))
    assert ok.status_code == 201, ok.text


def test_foreign_citizen_names_in_latin(client, db):
    pl = country_id(db, "PL")
    cyr = client.post("/api/auth/register", json=register_payload(citizenship_id=pl))
    assert cyr.status_code == 422
    ok = client.post("/api/auth/register", json=register_payload(
        citizenship_id=pl, last_name="Kowalski", first_name="Jan"))
    assert ok.status_code == 201


# ---------- login
def test_login_by_phone_and_by_email(client):
    client.post("/api/auth/register", json=register_payload())
    by_phone = login(client, "+380 50 123-45-67")
    assert by_phone.status_code == 200
    assert by_phone.json()["token_type"] == "bearer"
    assert by_phone.json()["user"]["role"] == "client"
    assert login(client, "TARAS@example.com").status_code == 200


def test_login_wrong_password_or_unknown_user(client):
    client.post("/api/auth/register", json=register_payload())
    wrong = login(client, "+380501234567", "Wrong-pass-123")
    unknown = login(client, "+380000000000")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]  # no hint which part was wrong


def test_blocked_user_cannot_login_or_use_old_token(client, db):
    client.post("/api/auth/register", json=register_payload())
    headers = auth_header(client)
    user = db.scalar(select(User).where(User.phone == "+380501234567"))
    user.is_active = False
    db.flush()
    assert login(client, "+380501234567").status_code == 401
    assert client.get("/api/auth/me", headers=headers).status_code == 401


# ---------- tokens and profile
def test_me_requires_valid_token(client, db):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    user = create_user(db, phone="+380501111111", email="a@a.ua", password=PASSWORD,
                       last_name="Тест", first_name="Тест")
    expired = create_access_token(user.id, user.role.value, expires_delta=timedelta(seconds=-1))
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_me_and_profile_update(client):
    client.post("/api/auth/register", json=register_payload())
    headers = auth_header(client)
    assert client.get("/api/auth/me", headers=headers).json()["first_name"] == "Тарас"
    response = client.patch("/api/auth/me", headers=headers,
                            json={"first_name": "Тарасик", "last_name": None})
    assert response.status_code == 200
    assert response.json()["first_name"] == "Тарасик"
    assert response.json()["last_name"] == "Шевченко"   # null ignored for required fields


def test_change_password(client):
    client.post("/api/auth/register", json=register_payload())
    headers = auth_header(client)
    bad = client.post("/api/auth/me/password", headers=headers,
                      json={"current_password": "nope-nope", "new_password": "New-pass-456"})
    assert bad.status_code == 422
    assert bad.json()["detail"] == [{"loc": ["body", "current_password"], "msg": "Поточний пароль невірний",
                                     "type": "profile_rule"}]
    ok = client.post("/api/auth/me/password", headers=headers,
                     json={"current_password": PASSWORD, "new_password": "New-pass-456"})
    assert ok.status_code == 204
    assert login(client, "+380501234567", "New-pass-456").status_code == 200


def test_new_password_must_differ(client):
    client.post("/api/auth/register", json=register_payload())
    response = client.post("/api/auth/me/password", headers=auth_header(client),
                           json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "new_password"]


def test_password_change_ends_every_session(client, db):
    """Tokens issued before the change (this tab's and other devices') stop working; a new
    login works. iat has whole seconds, so the old tokens are issued a few seconds earlier."""
    from datetime import datetime, timezone

    client.post("/api/auth/register", json=register_payload())
    user = db.scalar(select(User).where(User.phone == "+380501234567"))
    earlier = datetime.now(timezone.utc) - timedelta(seconds=5)
    old = {"Authorization": f"Bearer {create_access_token(user.id, 'client', issued_at=earlier)}"}
    other_device = {"Authorization": f"Bearer {create_access_token(user.id, 'client', issued_at=earlier)}"}
    assert client.post("/api/auth/me/password", headers=old,
                       json={"current_password": PASSWORD, "new_password": "New-pass-456"}).status_code == 204
    assert client.get("/api/auth/me", headers=old).status_code == 401
    assert client.get("/api/auth/me", headers=other_device).status_code == 401
    assert login(client, "+380501234567").status_code == 401          # the old password
    fresh = login(client, "+380501234567", "New-pass-456").json()["access_token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200


# ---------- personal account errors: 422 with the field (loc), the message for the client
def field_error(response, field):
    detail = response.json()["detail"]
    assert isinstance(detail, list) and detail[0]["loc"] == ["body", field], detail
    assert detail[0]["type"] == "profile_rule"
    return detail[0]["msg"]


def test_profile_email_taken_is_a_field_error(client, db):
    create_user(db, phone="+380509999999", email="taken@example.com", password=PASSWORD,
                last_name="Інший", first_name="Клієнт")
    client.post("/api/auth/register", json=register_payload())
    response = client.patch("/api/auth/me", headers=auth_header(client), json={"email": "Taken@Example.com"})
    assert response.status_code == 409
    assert field_error(response, "email") == "Користувач з таким e-mail вже існує"


def test_profile_email_is_saved_in_lower_case(client):
    client.post("/api/auth/register", json=register_payload())
    response = client.patch("/api/auth/me", headers=auth_header(client), json={"email": "New.Mail@Example.com"})
    assert response.status_code == 200 and response.json()["email"] == "new.mail@example.com"


def test_profile_names_follow_the_citizenship(client, db):
    """Changing only the citizenship is checked against the stored (Ukrainian) names."""
    client.post("/api/auth/register", json=register_payload())
    headers = auth_header(client)
    poland = country_id(db, "PL")
    response = client.patch("/api/auth/me", headers=headers, json={"citizenship_id": poland})
    assert response.status_code == 422
    assert field_error(response, "last_name") == "Прізвище та ім'я потрібно вводити латиницею"
    response = client.patch("/api/auth/me", headers=headers,
                            json={"citizenship_id": poland, "last_name": "Shevchenko", "first_name": "Тарас"})
    assert field_error(response, "first_name") == "Прізвище та ім'я потрібно вводити латиницею"
    response = client.patch("/api/auth/me", headers=headers, json={
        "citizenship_id": poland, "last_name": " Shevchenko ", "first_name": "Taras"})
    assert response.status_code == 200 and response.json()["last_name"] == "Shevchenko"


def test_profile_unknown_citizenship(client):
    client.post("/api/auth/register", json=register_payload())
    response = client.patch("/api/auth/me", headers=auth_header(client), json={"citizenship_id": 999999})
    assert field_error(response, "citizenship_id") == "Невідома країна громадянства"


@pytest.mark.parametrize("field, message", [("birth_date", "Вкажіть дату народження"),
                                            ("citizenship_id", "Оберіть громадянство")])
def test_client_cannot_clear_birth_date_or_citizenship(client, field, message):
    client.post("/api/auth/register", json=register_payload())
    headers = auth_header(client)
    response = client.patch("/api/auth/me", headers=headers, json={field: None})
    assert response.status_code == 422 and field_error(response, field) == message
    assert client.get("/api/auth/me", headers=headers).json()[field] is not None


def test_staff_may_clear_birth_date(client, db):
    create_user(db, phone="+380502222222", email="m@tour.ua", password=PASSWORD, last_name="Менеджер",
                first_name="Тест", role=UserRole.MANAGER, birth_date="1990-01-01")
    response = client.patch("/api/auth/me", headers=auth_header(client, "+380502222222"), json={"birth_date": None})
    assert response.status_code == 200 and response.json()["birth_date"] is None


def test_register_errors_stay_plain_text(client):
    """Registration keeps {"detail": "text"}: its form maps the texts (authErrors.ts)."""
    client.post("/api/auth/register", json=register_payload())
    response = client.post("/api/auth/register", json=register_payload(phone="+380507777777"))
    assert response.status_code == 409 and response.json()["detail"] == "Користувач з таким e-mail вже існує"


# ---------- roles
_probe = APIRouter()


@_probe.get("/_test/manager-only", dependencies=[Depends(require_roles(UserRole.MANAGER))])
def _manager_only():
    return {"ok": True}


app.include_router(_probe)


def test_require_roles(client, db):
    create_user(db, phone="+380502222222", email="m@tour.ua", password=PASSWORD,
                last_name="Менеджер", first_name="Тест", role=UserRole.MANAGER)
    create_user(db, phone="+380503333333", email="c@tour.ua", password=PASSWORD,
                last_name="Клієнт", first_name="Тест")
    manager = auth_header(client, "+380502222222")
    customer = auth_header(client, "+380503333333")
    assert client.get("/_test/manager-only", headers=manager).status_code == 200
    assert client.get("/_test/manager-only", headers=customer).status_code == 403
    assert client.get("/_test/manager-only").status_code == 401


# ---------- form 4.6.1.1, fields 6–7: birth date (18+) and citizenship are required
@pytest.mark.parametrize("missing", ["birth_date", "citizenship_id"])
def test_register_requires_birth_date_and_citizenship(client, missing):
    payload = register_payload()
    del payload[missing]
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", missing]


@pytest.fixture()
def kyiv_new_year(monkeypatch):
    """23:30 UTC on 31 Dec 2025 is already 1 Jan 2026 in Kyiv."""
    from datetime import datetime, timezone

    from app.services import clock
    monkeypatch.setattr(clock, "now", lambda: datetime(2025, 12, 31, 23, 30, tzinfo=timezone.utc))


@pytest.mark.parametrize("birth_date, ok", [
    ("2008-01-01", True),        # 18 today in Kyiv (still 31 Dec in UTC)
    ("2008-01-02", False),       # 18 tomorrow
    ("2030-01-01", False),       # in the future
])
def test_register_checks_age_by_the_kyiv_date(client, kyiv_new_year, birth_date, ok):
    response = client.post("/api/auth/register", json=register_payload(birth_date=birth_date))
    if ok:
        assert response.status_code == 201, response.text
    else:
        assert response.status_code == 422
        assert response.json()["detail"] == "Реєстрація доступна лише з 18 років"


def test_feb_29_birthday_turns_18_on_march_1():
    from datetime import date

    from app.services.users import age_on
    assert age_on(date(2008, 2, 29), date(2026, 2, 28)) == 17
    assert age_on(date(2008, 2, 29), date(2026, 3, 1)) == 18


def test_profile_birth_date_must_stay_adult(client):
    client.post("/api/auth/register", json=register_payload())
    headers = auth_header(client)
    refused = client.patch("/api/auth/me", json={"birth_date": "2020-01-01"}, headers=headers)
    assert refused.status_code == 422 and field_error(refused, "birth_date") == "Реєстрація доступна лише з 18 років"
    assert client.patch("/api/auth/me", json={"birth_date": "1985-03-03"}, headers=headers).status_code == 200


def test_staff_created_by_the_admin_need_no_birth_date(db):
    user = create_user(db, phone="+380501112233", email="m@tour.local", password=PASSWORD,
                       last_name="Менеджер", first_name="Тест", role=UserRole.MANAGER)
    assert user.birth_date is None and user.citizenship_id is None
