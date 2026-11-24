"""Guard for dev-only scripts: they must never run against the real (production) database.

Two independent checks, because one setting can be forgotten:
- APP_ENV must be "development" or "test" (the default is "production");
- a live Stripe key (sk_live_...) means real money, so it is refused whatever APP_ENV says.
"""
from app.config import settings

DEV_ENVIRONMENTS = ("development", "test")


def dev_guard_error() -> str | None:
    """The reason to refuse, or None when a dev-only script may run."""
    if settings.app_env not in DEV_ENVIRONMENTS:
        return (f"APP_ENV is '{settings.app_env}': this script is for development only. "
                f"Add APP_ENV=development to backend/.env on your own machine.")
    if settings.stripe_secret_key.startswith("sk_live_"):
        return "STRIPE_SECRET_KEY is a live key: dev-only scripts are refused."
    return None
