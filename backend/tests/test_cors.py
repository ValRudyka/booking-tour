"""CORS for the frontend dev server (Vite, http://localhost:5173), settings.cors_origins."""
from app.models.enums import UserRole
from tests.factories import headers_for, make_user

FRONTEND = "http://localhost:5173"


def preflight(client, origin):
    return client.options("/api/tours", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    })


def test_frontend_origin_is_allowed(client):
    response = preflight(client, FRONTEND)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    # No cookies are used, so the browser is not allowed to send credentials.
    assert "access-control-allow-credentials" not in response.headers

    response = client.get("/api/tours", headers={"Origin": FRONTEND})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND


def test_other_origin_gets_no_cors_headers(client):
    response = preflight(client, "http://evil.example")
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers

    response = client.get("/api/tours", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_maintenance_503_is_readable_by_the_frontend(client, db):
    """Without CORS headers on the 503 the browser would report a network error, and the
    catalog could not show «Технічні роботи»."""
    admin_headers = headers_for(make_user(db, role=UserRole.ADMIN))
    assert client.put("/api/admin/settings", json={"maintenance_mode": True},
                      headers=admin_headers).status_code == 200

    response = client.get("/api/tours", headers={"Origin": FRONTEND})
    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == FRONTEND
    assert "retry-after" in response.headers["access-control-expose-headers"].lower()
    # The preflight is answered by the middleware before the maintenance guard runs.
    assert preflight(client, FRONTEND).status_code == 200
