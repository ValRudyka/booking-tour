"""Client's cancellation request for a paid order (ТЗ 4.5.5, form 4.6.1.3)."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import AuditLog, Notification, Order, OrderDocument, Tour
from app.models.enums import CancelReason, OrderDocumentType, OrderStatus, UserRole
from tests.factories import headers_for, make_active_tour, make_order, make_paid_order, make_user

NOW = datetime.now(timezone.utc)
PDF = b"%PDF-1.4\n% hospital\n" + b"0" * 100
JPG = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture()
def tour(db, manager):
    return make_active_tour(db, manager)


def cancel_request(client, headers, order_id, reason="illness", accept=True, details=None, files=None):
    data = {"reason_code": reason, "accept_penalty_policy": str(accept).lower()}
    if details is not None:
        data["details"] = details
    return client.post(f"/api/orders/{order_id}/cancel-request", data=data, files=files, headers=headers)


@pytest.mark.parametrize("status", [OrderStatus.PAID, OrderStatus.IN_PROGRESS, OrderStatus.CONFIRMED,
                                    OrderStatus.DOCUMENTS_READY])
def test_request_from_each_allowed_status(client, db, customer, customer_headers, manager, tour, status):
    finance = make_user(db, role=UserRole.FINANCE)
    other_manager = make_user(db, role=UserRole.MANAGER)
    assigned = status != OrderStatus.PAID
    order = make_paid_order(db, customer, tour, status=status,
                            manager_id=manager.id if assigned else None)
    response = cancel_request(client, customer_headers, order.id, details=" Перелом ноги ")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["cancel_reason_code"], body["cancel_reason"]) == (
        "cancel_requested", "illness", "Перелом ноги")
    assert body["history"][-1]["comment"] == "Хвороба: Перелом ноги"
    assert body["history"][-1]["changed_by"] == customer.id
    assert db.get(Tour, tour.id).seats_sold == 2                 # seats come back only after the refund

    log = db.scalars(select(AuditLog).where(AuditLog.action == "cancel_requested")).one()
    assert log.user_id == customer.id and log.new_value["penalty_policy_accepted_at"]

    def notes(user):
        return db.scalars(select(Notification).where(Notification.user_id == user.id)).all()

    assert len(notes(finance)) == 1 and "ФПВ" in notes(finance)[0].body
    assert len(notes(manager)) == 1                              # the responsible one, or all
    assert len(notes(other_manager)) == (0 if assigned else 1)
    assert notes(customer) == []                                 # the client did it


@pytest.mark.parametrize("status", [OrderStatus.COMPLETED, OrderStatus.REJECTED, OrderStatus.CANCELLED,
                                    OrderStatus.CANCEL_REQUESTED, OrderStatus.ARCHIVED])
def test_request_refused_in_other_statuses(client, db, customer, customer_headers, tour, status):
    order = make_paid_order(db, customer, tour, status=status)
    response = cancel_request(client, customer_headers, order.id)
    assert response.status_code == 409 and "не можна подати" in response.json()["detail"]


def test_unpaid_order_is_cancelled_without_a_request(client, db, customer, customer_headers, tour):
    waiting = make_order(db, customer, tour, status=OrderStatus.AWAITING_PAYMENT,
                         hold_expires_at=NOW + timedelta(minutes=10))
    response = cancel_request(client, customer_headers, waiting.id)
    assert response.status_code == 409 and "одразу" in response.json()["detail"]
    assert client.post(f"/api/orders/{waiting.id}/cancel", headers=customer_headers).status_code == 200
    paid = make_paid_order(db, customer, tour)
    refused = client.post(f"/api/orders/{paid.id}/cancel", headers=customer_headers)
    assert refused.status_code == 409 and "клопотання" in refused.json()["detail"]


def test_consent_and_reason_are_required(client, db, customer, customer_headers, tour):
    order = make_paid_order(db, customer, tour)
    no_consent = cancel_request(client, customer_headers, order.id, accept=False)
    assert no_consent.status_code == 422 and "ФПВ" in no_consent.json()["detail"]
    assert cancel_request(client, customer_headers, order.id, reason="bored").status_code == 422
    assert client.post(f"/api/orders/{order.id}/cancel-request", data={"accept_penalty_policy": "true"},
                       headers=customer_headers).status_code == 422
    assert cancel_request(client, customer_headers, order.id, details="x" * 2001).status_code == 422
    assert db.get(Order, order.id).status == OrderStatus.PAID


def test_evidence_files_are_private_and_staff_only(client, db, customer, customer_headers, manager_headers,
                                                  tour):
    order = make_paid_order(db, customer, tour)
    response = cancel_request(client, customer_headers, order.id, reason="visa_refusal", files=[
        ("files", ("refusal.pdf", PDF, "application/pdf")), ("files", ("scan.jpg", JPG, "image/jpeg"))])
    assert response.status_code == 200, response.text
    docs = db.scalars(select(OrderDocument).where(OrderDocument.order_id == order.id)).all()
    assert {d.doc_type for d in docs} == {OrderDocumentType.CANCEL_EVIDENCE}
    assert all(d.file_path.startswith(f"private/orders/{order.id}/") for d in docs)
    assert client.get(f"/api/orders/{order.id}/documents", headers=customer_headers).json() == []

    detail = client.get(f"/api/manager/orders/{order.id}", headers=manager_headers).json()
    assert [d["doc_type"] for d in detail["documents"]] == ["cancel_evidence", "cancel_evidence"]
    download = client.get(f"/api/manager/orders/{order.id}/documents/{docs[0].id}/download",
                          headers=manager_headers)
    assert download.status_code == 200 and download.content == PDF


def test_evidence_type_and_count(client, db, customer, customer_headers, tour, monkeypatch):
    order = make_paid_order(db, customer, tour)
    png = cancel_request(client, customer_headers, order.id,
                         files=[("files", ("ok.pdf", PDF, "application/pdf")),
                                ("files", ("photo.png", PNG, "image/png"))])
    assert png.status_code == 422 and "PDF або JPG" in png.json()["detail"]
    folder = Path(settings.upload_dir) / "private" / "orders" / str(order.id)
    assert not folder.exists() or not any(folder.iterdir())
    monkeypatch.setattr(settings, "max_cancel_evidence_files", 1)
    many = cancel_request(client, customer_headers, order.id,
                          files=[("files", ("a.pdf", PDF, "application/pdf")),
                                 ("files", ("b.pdf", PDF, "application/pdf"))])
    assert many.status_code == 422
    assert db.get(Order, order.id).status == OrderStatus.PAID


def test_access(client, db, customer, tour, manager_headers):
    order = make_paid_order(db, customer, tour)
    assert cancel_request(client, headers_for(make_user(db)), order.id).status_code == 404
    assert cancel_request(client, manager_headers, order.id).status_code == 403
    assert cancel_request(client, {}, order.id).status_code == 401
    assert CancelReason("other")
