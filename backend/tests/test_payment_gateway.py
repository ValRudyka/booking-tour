"""Gateway selection and the Stripe gateway's webhook parsing (no network)."""
import json
import time

import pytest

from app.config import settings
from app.services.payments import gateway as gateway_module
from app.services.payments.gateway import InvalidSignature, gateway_name, get_gateway, set_gateway
from app.services.payments.mock_gateway import MockGateway
from app.services.payments.stripe_gateway import StripeGateway
from tests.factories import stripe_signature

SECRET = "whsec_test_secret"
EVENT = {"id": "evt_1", "object": "event", "type": "checkout.session.completed",
         "data": {"object": {"id": "cs_test_1", "object": "checkout.session", "status": "complete",
                             "payment_status": "paid", "payment_intent": "pi_1",
                             "amount_total": 7750000,
                             "metadata": {"order_id": "1", "payment_id": "2"}}}}


@pytest.mark.parametrize("configured,key,expected", [
    ("", "", "mock"), ("", "sk_test_x", "stripe"), ("mock", "sk_test_x", "mock"),
    ("STRIPE", "sk_test_x", "stripe"),
])
def test_gateway_choice(monkeypatch, configured, key, expected):
    monkeypatch.setattr(settings, "payment_gateway", configured)
    monkeypatch.setattr(settings, "stripe_secret_key", key)
    assert gateway_name() == expected


def test_wrong_gateway_name(monkeypatch):
    monkeypatch.setattr(settings, "payment_gateway", "paypal")
    with pytest.raises(ValueError):
        gateway_name()


def test_stripe_without_key_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "payment_gateway", "stripe")
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    set_gateway(None)
    with pytest.raises(RuntimeError):
        get_gateway()


def test_tests_use_the_mock():
    assert isinstance(get_gateway(), MockGateway)
    assert gateway_module.settings.stripe_secret_key == ""


def stripe_gateway(secret=SECRET):
    return StripeGateway("sk_test_dummy_not_used", secret, settings.stripe_api_version)


def test_stripe_webhook_valid_signature():
    payload = json.dumps(EVENT).encode()
    event = stripe_gateway().parse_webhook(payload, stripe_signature(payload, SECRET))
    assert (event.id, event.type) == ("evt_1", "checkout.session.completed")
    session = event.session
    assert (session.id, session.status, session.payment_status, session.payment_intent,
            session.amount_total, session.metadata) == (
        "cs_test_1", "complete", "paid", "pi_1", 7750000, {"order_id": "1", "payment_id": "2"})


@pytest.mark.parametrize("header", [
    None, "", "t=1,v1=deadbeef", "garbage",
])
def test_stripe_webhook_bad_signature(header):
    with pytest.raises(InvalidSignature):
        stripe_gateway().parse_webhook(json.dumps(EVENT).encode(), header)


def test_stripe_webhook_signed_with_other_secret_or_too_old():
    payload = json.dumps(EVENT).encode()
    with pytest.raises(InvalidSignature):
        stripe_gateway().parse_webhook(payload, stripe_signature(payload, "whsec_other"))
    old = int(time.time()) - 600                      # older than the 5-minute tolerance
    with pytest.raises(InvalidSignature):
        stripe_gateway().parse_webhook(payload, stripe_signature(payload, SECRET, old))


def test_stripe_webhook_without_configured_secret():
    payload = json.dumps(EVENT).encode()
    with pytest.raises(InvalidSignature):
        stripe_gateway(secret="").parse_webhook(payload, stripe_signature(payload, SECRET))


def test_other_event_types_have_no_session():
    event = {"id": "evt_2", "object": "event", "type": "charge.refunded",
             "data": {"object": {"id": "ch_1", "object": "charge"}}}
    payload = json.dumps(event).encode()
    parsed = stripe_gateway().parse_webhook(payload, stripe_signature(payload, SECRET))
    assert parsed.session is None
