"""Stripe webhook, the payment return page and the mock payment page (dev only)."""
import logging
from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.deps import DbSession
from app.models.enums import PaymentStatus, TransactionStatus
from app.schemas.payments import PaymentResultOut
from app.services.errors import DomainError
from app.services.payments import service as payment_service
from app.services.payments.gateway import GatewayError, InvalidSignature, PaymentGateway, get_gateway
from app.services.payments.mock_gateway import MockGateway

router = APIRouter(prefix="/payments", tags=["payments"])
logger = logging.getLogger("tour.payments")

Gateway = Annotated[PaymentGateway, Depends(get_gateway)]


@router.post("/stripe/webhook", summary="Події Stripe (перевірка підпису)", include_in_schema=False)
async def stripe_webhook(request: Request, db: DbSession, gateway: Gateway):
    """The raw body is needed for the signature check, so this endpoint is async; the database
    work is synchronous and runs in a worker thread. 2xx = handled or ignored; 400 = not signed by
    Stripe; 503 = temporary failure (e.g. a refund call failed) -> Stripe retries the event."""
    payload = await request.body()
    try:
        event = gateway.parse_webhook(payload, request.headers.get("Stripe-Signature"))
    except InvalidSignature:
        return JSONResponse({"detail": "Невірний підпис вебхука"}, status_code=400)

    def process() -> str:
        # A savepoint: if the refund call fails, everything this event changed is undone and
        # nothing is committed, so the retried event starts from the same state.
        with db.begin_nested():
            result = payment_service.handle_event(db, event, gateway)
        db.commit()
        return result

    try:
        result = await run_in_threadpool(process)
    except GatewayError as error:
        logger.error("Event %s not processed, Stripe will retry: %s", event.id, error)
        return JSONResponse({"detail": "Тимчасова помилка, повторіть пізніше"}, status_code=503)
    logger.info("Stripe event %s (%s): %s", event.id, event.type, result)
    return {"received": True, "result": result}


MESSAGES = {
    PaymentStatus.PAID: "Оплату отримано, дякуємо! Замовлення передано менеджеру.",
    PaymentStatus.REFUNDED: "Оплата надійшла запізно — кошти автоматично повернено на картку.",
}


@router.get("/result", response_model=PaymentResultOut, summary="Результат оплати (повернення зі Stripe)")
def payment_result(db: DbSession, session_id: Annotated[str, Query(max_length=255)],
                   cancelled: bool = False):
    """Opened by the client's browser after Stripe, so there is no token: the unguessable
    session id is the key, and only statuses are shown."""
    try:
        payment = payment_service.payment_result(db, session_id)
    except DomainError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from None
    order = payment.order
    if order.payment_status in MESSAGES:
        message = MESSAGES[order.payment_status]
    elif cancelled or payment.status == TransactionStatus.FAILED:
        message = "Оплату не завершено. Ви можете спробувати ще раз, поки діє бронювання."
    else:
        message = "Очікуємо підтвердження оплати від банку — оновіть сторінку за хвилину."
    return PaymentResultOut(order_number=order.number, order_status=order.status,
                            payment_status=order.payment_status, payment=payment.status,
                            message=message)


# ---------- mock gateway (dev only): plays the Stripe payment page
def _mock(gateway: PaymentGateway) -> MockGateway:
    if not isinstance(gateway, MockGateway):
        raise HTTPException(status_code=404, detail="Не знайдено")
    return gateway


@router.get("/mock/{session_id}", response_class=HTMLResponse, include_in_schema=False)
def mock_checkout_page(session_id: str, gateway: Gateway):
    mock = _mock(gateway)
    try:
        session = mock.retrieve_checkout_session(session_id)
    except GatewayError:
        raise HTTPException(status_code=404, detail="Сесію оплати не знайдено") from None
    sid = escape(session_id)
    amount = payment_service.from_minor(session.amount_total or 0)
    return f"""<!doctype html><meta charset="utf-8"><title>Тестова оплата</title>
<h1>Тестова оплата (mock)</h1>
<p>Замовлення {escape(session.metadata.get("order_number", ""))}, сума {amount} грн,
статус сесії: {escape(session.status)}.</p>
<form method="post" action="/api/payments/mock/{sid}/succeed"><button>Оплата успішна</button></form>
<form method="post" action="/api/payments/mock/{sid}/expire"><button>Сесія минула</button></form>"""


def _mock_event(db, gateway: PaymentGateway, session_id: str, succeed: bool) -> dict:
    mock = _mock(gateway)
    try:
        event = mock.complete(session_id) if succeed else mock.expire(session_id)
    except GatewayError:
        raise HTTPException(status_code=404, detail="Сесію оплати не знайдено") from None
    result = payment_service.handle_event(db, event, mock)
    db.commit()
    return {"event": event.type, "result": result}


@router.post("/mock/{session_id}/succeed", include_in_schema=False)
def mock_succeed(session_id: str, db: DbSession, gateway: Gateway):
    return _mock_event(db, gateway, session_id, succeed=True)


@router.post("/mock/{session_id}/expire", include_in_schema=False)
def mock_expire(session_id: str, db: DbSession, gateway: Gateway):
    return _mock_event(db, gateway, session_id, succeed=False)
