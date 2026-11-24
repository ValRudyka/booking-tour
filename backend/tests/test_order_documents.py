"""Order documents: private storage, upload rules, «Документи готові», client downloads."""
from datetime import timedelta
from pathlib import Path

import pytest

from app.config import settings
from app.models import OrderDocument
from app.models.enums import OrderDocumentType, OrderStatus, UserRole
from app.services import clock
from tests.factories import headers_for, make_active_tour, make_paid_order, make_user

URL = "/api/manager/orders"
PDF = b"%PDF-1.4\n% voucher\n" + b"0" * 300
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture()
def order(db, customer, manager):
    tour = make_active_tour(db, manager)
    return make_paid_order(db, customer, tour, status=OrderStatus.CONFIRMED, manager_id=manager.id,
                           start_date=tour.departure_from, end_date=tour.departure_from + timedelta(days=7),
                           pnr="ABC123", operator_deadline=clock.today() + timedelta(days=5))


def upload(client, headers, order_id, doc_type="voucher", files=None):
    files = files or [("files", ("voucher.pdf", PDF, "application/pdf"))]
    return client.post(f"{URL}/{order_id}/documents", data={"doc_type": doc_type}, files=files,
                       headers=headers)


def stored(db, doc_id) -> Path:
    return Path(settings.upload_dir) / db.get(OrderDocument, doc_id).file_path


def test_upload_is_private(client, db, manager, manager_headers, order):
    response = upload(client, manager_headers, order.id, files=[
        ("files", ("../../evil.pdf", PDF, "application/pdf")), ("files", ("map.png", PNG, "image/png"))])
    assert response.status_code == 201, response.text
    first, second = response.json()
    assert (first["doc_type"], first["uploaded_by"]) == ("voucher", manager.id)
    doc = db.get(OrderDocument, first["id"])
    assert doc.file_path.startswith(f"private/orders/{order.id}/") and doc.file_path.endswith(".pdf")
    assert "evil" not in doc.file_path and stored(db, second["id"]).suffix == ".png"
    assert stored(db, first["id"]).read_bytes() == PDF
    # Not reachable through the public mount, whatever the path.
    assert client.get(f"/uploads/{doc.file_path}").status_code == 404
    assert client.get(f"/uploads/tours/../{doc.file_path}").status_code == 404
    download = client.get(f"{URL}/{order.id}/documents/{first['id']}/download", headers=manager_headers)
    assert download.status_code == 200 and download.content == PDF
    assert download.headers["content-type"] == "application/pdf"
    assert f"voucher-{order.number}-{first['id']}.pdf" in download.headers["content-disposition"]


def test_wrong_type_and_size(client, db, manager_headers, order, monkeypatch):
    bad = upload(client, manager_headers, order.id,
                 files=[("files", ("ok.pdf", PDF, "application/pdf")),
                        ("files", ("virus.pdf", b"MZ not a pdf", "application/pdf"))])
    assert bad.status_code == 422 and "virus.pdf" in bad.json()["detail"]
    folder = Path(settings.upload_dir) / "private" / "orders" / str(order.id)
    assert not folder.exists() or not any(folder.iterdir())          # nothing half-saved
    assert db.query(OrderDocument).filter_by(order_id=order.id).count() == 0
    assert upload(client, manager_headers, order.id, doc_type="cancel_evidence").status_code == 422
    assert upload(client, manager_headers, order.id, doc_type="passport_scan").status_code == 422
    monkeypatch.setattr(settings, "max_document_mb", 0)
    assert upload(client, manager_headers, order.id).status_code == 413
    monkeypatch.setattr(settings, "max_document_mb", 10)
    monkeypatch.setattr(settings, "max_documents_per_order", 1)
    assert upload(client, manager_headers, order.id).status_code == 201
    assert upload(client, manager_headers, order.id).status_code == 409


def test_upload_only_after_confirmation(client, db, manager_headers, order):
    order.status = OrderStatus.IN_PROGRESS            # test setup only; the app uses change_status
    db.flush()
    response = upload(client, manager_headers, order.id)
    assert response.status_code == 409 and "після підтвердження" in response.json()["detail"]


def test_documents_ready_needs_a_voucher(client, db, manager_headers, order):
    ready = f"{URL}/{order.id}/documents-ready"
    assert upload(client, manager_headers, order.id, doc_type="air_ticket").status_code == 201
    response = client.post(ready, headers=manager_headers)
    assert response.status_code == 409 and "ваучер" in response.json()["detail"]
    upload(client, manager_headers, order.id)
    response = client.post(ready, json={"client_message": "Гарного відпочинку!"}, headers=manager_headers)
    assert response.status_code == 200 and response.json()["status"] == "documents_ready"
    assert client.post(ready, headers=manager_headers).status_code == 409


def test_delete_document(client, db, manager_headers, order):
    voucher = upload(client, manager_headers, order.id).json()[0]["id"]
    ticket = upload(client, manager_headers, order.id, doc_type="air_ticket").json()[0]["id"]
    path = stored(db, ticket)
    assert client.delete(f"{URL}/{order.id}/documents/{ticket}", headers=manager_headers).status_code == 204
    assert not path.exists() and db.get(OrderDocument, ticket) is None
    client.post(f"{URL}/{order.id}/documents-ready", headers=manager_headers)
    last = client.delete(f"{URL}/{order.id}/documents/{voucher}", headers=manager_headers)
    assert last.status_code == 409 and "останній ваучер" in last.json()["detail"]
    second = upload(client, manager_headers, order.id).json()[0]["id"]
    assert client.delete(f"{URL}/{order.id}/documents/{voucher}", headers=manager_headers).status_code == 204
    assert client.delete(f"{URL}/{order.id}/documents/{voucher}", headers=manager_headers).status_code == 404
    assert db.get(OrderDocument, second) is not None


def test_client_downloads_own_documents_only(client, db, customer, customer_headers, manager,
                                             manager_headers, order):
    doc_id = upload(client, manager_headers, order.id).json()[0]["id"]
    evidence = OrderDocument(order_id=order.id, doc_type=OrderDocumentType.CANCEL_EVIDENCE,
                             file_path=db.get(OrderDocument, doc_id).file_path, uploaded_by=customer.id)
    db.add(evidence)
    db.flush()

    listed = client.get(f"/api/orders/{order.id}/documents", headers=customer_headers)
    assert [d["id"] for d in listed.json()] == [doc_id]                   # trip documents only
    own = client.get(f"/api/orders/{order.id}/documents/{doc_id}/download", headers=customer_headers)
    assert own.status_code == 200 and own.content == PDF
    assert client.get(f"/api/orders/{order.id}/documents/{evidence.id}/download",
                      headers=customer_headers).status_code == 404

    stranger = headers_for(make_user(db))
    assert client.get(f"/api/orders/{order.id}/documents", headers=stranger).status_code == 404
    assert client.get(f"/api/orders/{order.id}/documents/{doc_id}/download",
                      headers=stranger).status_code == 404
    assert client.get(f"/api/orders/{order.id}/documents/{doc_id}/download").status_code == 401
    finance = headers_for(make_user(db, role=UserRole.FINANCE))
    assert client.get(f"{URL}/{order.id}/documents/{doc_id}/download", headers=finance).status_code == 403


def test_client_sees_nothing_before_confirmation(client, db, customer, customer_headers, manager,
                                                manager_headers, order):
    doc_id = upload(client, manager_headers, order.id).json()[0]["id"]
    order.status = OrderStatus.CANCEL_REQUESTED       # documents no longer valid for the trip
    db.flush()
    assert client.get(f"/api/orders/{order.id}/documents", headers=customer_headers).json() == []
    assert client.get(f"/api/orders/{order.id}/documents/{doc_id}/download",
                      headers=customer_headers).status_code == 404
    for status in (OrderStatus.DOCUMENTS_READY, OrderStatus.COMPLETED, OrderStatus.ARCHIVED):
        order.status = status
        db.flush()
        assert len(client.get(f"/api/orders/{order.id}/documents", headers=customer_headers).json()) == 1
