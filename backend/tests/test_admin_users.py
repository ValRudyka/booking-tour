"""Administrator: staff accounts, roles, blocking, password reset and their safety rules."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models import AuditLog, User
from app.models.enums import UserRole
from tests.factories import headers_for, make_user

URL = "/api/admin/users"


@pytest.fixture()
def admin(db):
    return make_user(db, role=UserRole.ADMIN)


@pytest.fixture()
def admin_headers(admin):
    return headers_for(admin)


def staff(role="manager", phone="+380671112233", email="new.staff@tour.ua", password="Staff-pass-1"):
    return {"role": role, "phone": phone, "email": email, "password": password,
            "last_name": "Коваль", "first_name": "Олена"}


def login(client, username, password):
    return client.post("/api/auth/login", data={"username": username, "password": password})


def logs(db, user_id, action=None):
    query = select(AuditLog).where(AuditLog.entity == "user", AuditLog.entity_id == str(user_id))
    if action:
        query = query.where(AuditLog.action == action)
    return db.scalars(query.order_by(AuditLog.id)).all()


# ---------- create staff
def test_create_staff_who_can_log_in(client, db, admin, admin_headers):
    response = client.post(URL, json=staff(), headers=admin_headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["role"], body["is_active"], body["email"]) == ("manager", True, "new.staff@tour.ua")
    token = login(client, "+380671112233", "Staff-pass-1")
    assert token.status_code == 200 and token.json()["user"]["role"] == "manager"
    [entry] = logs(db, body["id"], "created")
    assert entry.user_id == admin.id and entry.new_value["role"] == "manager"
    assert "Staff-pass-1" not in str(entry.new_value) and "password" not in str(entry.new_value)


def test_create_staff_validation(client, db, admin_headers):
    client_role = client.post(URL, json=staff(role="client"), headers=admin_headers)
    assert client_role.status_code == 422 and "клієнти реєструються самі" in client_role.json()["detail"]
    assert client.post(URL, json=staff(password="short"), headers=admin_headers).status_code == 422
    assert client.post(URL, json=staff(phone="12345"), headers=admin_headers).status_code == 422
    assert client.post(URL, json=staff(), headers=admin_headers).status_code == 201
    duplicate = client.post(URL, json=staff(email="other@tour.ua"), headers=admin_headers)
    assert duplicate.status_code == 409 and "телефоном" in duplicate.json()["detail"]


# ---------- list
def test_filters_and_search(client, db, admin_headers):
    manager = make_user(db, role=UserRole.MANAGER, email="kovalenko@tour.ua")
    blocked = make_user(db, role=UserRole.FINANCE)
    blocked.is_active = False
    make_user(db)
    db.flush()

    def ids(**params):
        return {u["id"] for u in client.get(URL, params=params, headers=admin_headers).json()["items"]}

    assert manager.id in ids(role="manager") and blocked.id not in ids(role="manager")
    assert ids(is_active=False) == {blocked.id}
    assert ids(q="kovalenko") == {manager.id}
    assert ids(q=manager.phone[-7:]) == {manager.id}
    page = client.get(URL, params={"page_size": 2}, headers=admin_headers).json()
    assert len(page["items"]) == 2 and page["total"] >= 4


# ---------- role change and blocking take effect at once
def test_role_change_applies_to_the_old_token(client, db, admin, admin_headers):
    manager = make_user(db, role=UserRole.MANAGER)
    token = headers_for(manager)                                # issued while a manager
    assert client.get("/api/manager/orders", headers=token).status_code == 200
    response = client.patch(f"{URL}/{manager.id}", json={"role": "finance"}, headers=admin_headers)
    assert response.status_code == 200 and response.json()["role"] == "finance"
    assert client.get("/api/manager/orders", headers=token).status_code == 403
    assert client.get("/api/finance/payments", headers=token).status_code == 200
    [entry] = logs(db, manager.id, "role_changed")
    assert (entry.old_value, entry.new_value) == ({"role": "manager"}, {"role": "finance"})


def test_block_rejects_the_old_token_and_unblock_restores(client, db, admin_headers):
    manager = make_user(db, role=UserRole.MANAGER)
    token = headers_for(manager)
    assert client.patch(f"{URL}/{manager.id}", json={"is_active": False}, headers=admin_headers).status_code == 200
    assert client.get("/api/auth/me", headers=token).status_code == 401
    assert client.patch(f"{URL}/{manager.id}", json={"is_active": True}, headers=admin_headers).status_code == 200
    assert client.get("/api/auth/me", headers=token).status_code == 200
    assert [e.action for e in logs(db, manager.id)] == ["blocked", "unblocked"]


def test_client_role_cannot_change_but_client_can_be_blocked(client, db, admin_headers):
    customer = make_user(db)
    response = client.patch(f"{URL}/{customer.id}", json={"role": "manager"}, headers=admin_headers)
    assert response.status_code == 409 and "Роль клієнта не змінюється" in response.json()["detail"]
    manager = make_user(db, role=UserRole.MANAGER)
    assert client.patch(f"{URL}/{manager.id}", json={"role": "client"}, headers=admin_headers).status_code == 422
    assert client.patch(f"{URL}/{customer.id}", json={"is_active": False}, headers=admin_headers).status_code == 200


def test_edit_profile_fields(client, db, admin_headers):
    manager = make_user(db, role=UserRole.MANAGER)
    other = make_user(db)
    response = client.patch(f"{URL}/{manager.id}", json={"last_name": "Бондар", "email": "BONDAR@tour.ua"},
                            headers=admin_headers)
    assert response.status_code == 200 and response.json()["email"] == "bondar@tour.ua"
    assert client.patch(f"{URL}/{manager.id}", json={"phone": other.phone},
                        headers=admin_headers).status_code == 409
    assert client.patch(f"{URL}/{manager.id}", json={"password_hash": "x"},
                        headers=admin_headers).status_code == 422
    [entry] = logs(db, manager.id, "updated")
    assert entry.new_value == {"last_name": "Бондар", "email": "bondar@tour.ua"}


# ---------- safety rules
def test_admin_cannot_block_or_demote_themselves(client, db, admin, admin_headers):
    make_user(db, role=UserRole.ADMIN)                          # not the last admin
    for change in ({"is_active": False}, {"role": "manager"}):
        response = client.patch(f"{URL}/{admin.id}", json=change, headers=admin_headers)
        assert response.status_code == 409 and "себе" in response.json()["detail"]
    assert client.patch(f"{URL}/{admin.id}", json={"last_name": "Новий"}, headers=admin_headers).status_code == 200


def test_last_active_admin_stays(client, db, admin, admin_headers):
    """Other admins can be demoted until only one active admin is left."""
    for other in db.scalars(select(User).where(User.role == UserRole.ADMIN, User.id != admin.id)):
        other.is_active = False                                 # e.g. seeded admins of the dev DB
    second = make_user(db, role=UserRole.ADMIN)
    second_headers = headers_for(second)
    assert client.patch(f"{URL}/{admin.id}", json={"role": "manager"}, headers=second_headers).status_code == 200
    # Now `second` is the only active admin; a blocked admin does not count.
    blocked_admin = make_user(db, role=UserRole.ADMIN)
    blocked_admin.is_active = False
    db.flush()
    third = make_user(db, role=UserRole.ADMIN)
    assert client.patch(f"{URL}/{third.id}", json={"is_active": False}, headers=second_headers).status_code == 200
    db.expire_all()
    remaining = db.scalars(select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))).all()
    assert [u.id for u in remaining] == [second.id]
    # Only another admin could act on `second`, and there is none; the rule itself:
    from app.services.admin_users import update_user
    from app.services.errors import DomainError

    with pytest.raises(DomainError, match="останній активний адміністратор"):
        update_user(db, blocked_admin, second.id, {"is_active": False})
    with pytest.raises(DomainError, match="останній активний адміністратор"):
        update_user(db, blocked_admin, second.id, {"role": UserRole.FINANCE})


# ---------- password reset and the token cut-off
def test_reset_password_ends_old_sessions(client, db, admin, admin_headers):
    manager = make_user(db, role=UserRole.MANAGER, phone="+380671230000")
    manager.password_hash = hash_password("Old-pass-11")
    db.flush()
    old_token = {"Authorization": f"Bearer {login(client, '+380671230000', 'Old-pass-11').json()['access_token']}"}
    response = client.post(f"{URL}/{manager.id}/reset-password", json={"new_password": "New-pass-22"},
                           headers=admin_headers)
    assert response.status_code == 200
    db.refresh(manager)
    cutoff = manager.tokens_valid_after
    assert cutoff is not None and cutoff.microsecond == 0          # whole seconds, like JWT iat

    # Logging in right away — in the same second as the reset — gives a working token.
    fresh = login(client, "+380671230000", "New-pass-22")
    assert fresh.status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh.json()['access_token']}"}
                      ).status_code == 200
    same_second = {"Authorization": f"Bearer {create_access_token(manager.id, 'manager', issued_at=cutoff + timedelta(microseconds=999_999))}"}
    assert client.get("/api/auth/me", headers=same_second).status_code == 200
    # A token issued in an earlier second is rejected.
    earlier = {"Authorization": f"Bearer {create_access_token(manager.id, 'manager', issued_at=cutoff - timedelta(seconds=1))}"}
    assert client.get("/api/auth/me", headers=earlier).status_code == 401
    assert login(client, "+380671230000", "Old-pass-11").status_code == 401

    [entry] = logs(db, manager.id, "password_reset")
    text = str(entry.new_value) + str(entry.old_value)
    assert "New-pass-22" not in text and "$argon2" not in text and "sessions_ended_at" in text


def test_token_without_iat_is_rejected_after_a_reset(client, db, admin_headers):
    import jwt

    from app.config import settings

    manager = make_user(db, role=UserRole.MANAGER)
    legacy = jwt.encode({"sub": str(manager.id), "role": "manager"}, settings.secret_key,
                        algorithm=settings.jwt_algorithm)                # issued before iat existed
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 200
    client.post(f"{URL}/{manager.id}/reset-password", json={"new_password": "New-pass-22"}, headers=admin_headers)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 401


def test_reset_validation_and_unknown_user(client, admin_headers):
    assert client.post(f"{URL}/999999/reset-password", json={"new_password": "New-pass-22"},
                       headers=admin_headers).status_code == 404
    assert client.patch(f"{URL}/999999", json={"is_active": False}, headers=admin_headers).status_code == 404


# ---------- access
@pytest.mark.parametrize("role", [UserRole.CLIENT, UserRole.MANAGER, UserRole.FINANCE])
def test_admin_users_only_for_admins(client, db, role):
    headers = headers_for(make_user(db, role=role))
    target = make_user(db, role=UserRole.MANAGER)
    for call in (lambda h: client.get(URL, headers=h),
                 lambda h: client.get(f"{URL}/{target.id}", headers=h),
                 lambda h: client.post(URL, json=staff(), headers=h),
                 lambda h: client.patch(f"{URL}/{target.id}", json={"is_active": False}, headers=h),
                 lambda h: client.post(f"{URL}/{target.id}/reset-password", json={"new_password": "New-pass-22"},
                                       headers=h)):
        assert call(headers).status_code == 403
        assert call({}).status_code == 401
