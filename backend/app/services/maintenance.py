"""Maintenance mode «Технічні роботи» (form 4.6.4.1, field 7; ТЗ 5.1 service mode).

An app-wide FastAPI dependency (app/main.py), so it uses the same database session as the
endpoints. When settings.maintenance_mode is on, every request gets 503 with a Ukrainian message
and Retry-After, except:
- GET /health, /docs, /redoc, /openapi.json — monitoring and API docs, no data;
- POST /api/auth/login — passwords are checked as usual (a wrong one is still 401), but anyone
  except an admin gets 503 instead of a token (routers/auth.py), so only admins can log in;
- GET /api/auth/me for an admin — the admin interface needs to know who is logged in;
- /api/admin/... — admin only anyway, including switching maintenance off;
- POST /api/payments/stripe/webhook — money already paid must still be recorded or refunded;
- GET /api/site/contacts — how to reach support, most useful exactly while the site is down.
Managers and finance are stopped too. The System jobs (hold expiry, completion) keep running, and
tour photos (/uploads/tours, static files) stay available.
"""
from fastapi import HTTPException, Request, status

from app.core.deps import DbSession, user_from_token
from app.models.enums import UserRole
from app.services.app_settings import get_setting

MESSAGE = "Тривають технічні роботи. Спробуйте пізніше."
RETRY_AFTER_SEC = "600"
OPEN_PATHS = frozenset({"/health", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json",
                        "/api/auth/login", "/api/payments/stripe/webhook", "/api/site/contacts"})
ADMIN_PREFIX = "/api/admin"


def is_on(db) -> bool:
    return bool(get_setting(db, "maintenance_mode", False))


def unavailable() -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=MESSAGE,
                         headers={"Retry-After": RETRY_AFTER_SEC})


def _bearer(request: Request) -> str | None:
    """Read the token by hand: an OAuth2 dependency here would mark every endpoint as secured
    in the OpenAPI docs."""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return token if scheme.lower() == "bearer" and token else None


def guard(request: Request, db: DbSession) -> None:
    path = request.url.path.rstrip("/") or "/"
    if path in OPEN_PATHS or path == ADMIN_PREFIX or path.startswith(ADMIN_PREFIX + "/"):
        return
    if not is_on(db):
        return
    if path == "/api/auth/me":
        user = user_from_token(db, _bearer(request))
        if user is not None and user.role == UserRole.ADMIN:
            return
    raise unavailable()
