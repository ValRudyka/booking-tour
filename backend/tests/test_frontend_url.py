"""Where Stripe sends the client back (spec 05) and the production guard for FRONTEND_URL."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.config import (DEV_FRONTEND_URL, FRONTEND_URL_MISSING, Settings, check_startup_settings,
                        frontend_base_url, settings)
from app.models.enums import OrderStatus
from app.services.payments.service import return_urls
from tests.factories import make_active_tour, make_order


def config(**values) -> Settings:
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_empty_frontend_url_is_the_vite_dev_server_in_dev_and_test(app_env):
    assert frontend_base_url(config(app_env=app_env, frontend_url="")) == DEV_FRONTEND_URL


def test_frontend_url_is_used_without_a_trailing_slash():
    assert frontend_base_url(config(app_env="production",
                                    frontend_url=" https://tour.example.com/ ")) == "https://tour.example.com"


def test_production_without_frontend_url_is_refused():
    production = config(app_env="production", frontend_url="")
    with pytest.raises(RuntimeError, match="FRONTEND_URL is not set"):
        check_startup_settings(production)
    check_startup_settings(config(app_env="production", frontend_url="https://tour.example.com"))


def test_the_api_does_not_start_in_production_without_frontend_url(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "frontend_url", "")
    with pytest.raises(RuntimeError) as error:
        with TestClient(main_module.app):
            pass
    assert str(error.value) == FRONTEND_URL_MISSING


def test_return_urls_point_to_the_frontend_pages_with_the_order(db, manager, customer, monkeypatch):
    order = make_order(db, customer, make_active_tour(db, manager), status=OrderStatus.AWAITING_PAYMENT,
                       total_uah=Decimal("1000.00"))
    monkeypatch.setattr(settings, "frontend_url", "https://tour.example.com/")
    assert return_urls(order) == (
        f"https://tour.example.com/payment/success?order_id={order.id}&session_id={{CHECKOUT_SESSION_ID}}",
        f"https://tour.example.com/payment/cancel?order_id={order.id}",
    )
    monkeypatch.setattr(settings, "frontend_url", "")          # APP_ENV=test in the tests
    assert return_urls(order)[1] == f"{DEV_FRONTEND_URL}/payment/cancel?order_id={order.id}"
