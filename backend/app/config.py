"""Application settings, read from environment variables or the backend/.env file."""
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Where the app runs. Dev-only tools (scripts.seed_demo, complete_orders --force) refuse to run
    # unless this is "development" or "test". The default is "production" on purpose: a server
    # whose .env forgot the setting is treated as the real one.
    app_env: Literal["development", "test", "production"] = "production"

    database_url: str = "postgresql+psycopg://tour_app:change_me@localhost:5432/tour_website"
    sql_echo: bool = False

    # JWT. Generate your own key: python -c "import secrets; print(secrets.token_hex(32))"
    secret_key: str = "dev-insecure-key-change-me-in-env-file-0000000000"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Uploaded files. Only upload_dir/tours (tour photos) is public, at /uploads/tours/...
    upload_dir: Path = BACKEND_DIR / "uploads"
    max_image_mb: int = 5
    max_images_per_tour: int = 20

    # How often the server cancels orders whose seat hold ran out; 0 turns the loop off.
    order_expiry_interval_sec: int = 60

    # Payments. PAYMENT_GATEWAY = "stripe" | "mock"; empty = stripe if a secret key is set, else mock.
    payment_gateway: str = ""
    stripe_secret_key: str = ""          # test-mode key only; never commit it
    stripe_webhook_secret: str = ""      # whsec_... from `stripe listen` or the Dashboard
    stripe_api_version: str = "2026-11-18.endive"
    # Where Stripe sends the client back. Empty until the frontend exists: then the API's own
    # result page at API_BASE_URL/api/payments/result is used.
    frontend_url: str = ""
    api_base_url: str = "http://127.0.0.1:8000"
    # Bank transfer details shown to the client (demo values; set real ones in .env).
    bank_recipient: str = "ТОВ «Демо Тур» (демонстраційні реквізити)"
    bank_iban: str = "UA000000000000000000000000000"
    bank_edrpou: str = "00000000"
    bank_name: str = "Демо-банк"
    max_statement_mb: int = 10           # bank statement uploaded by the finance controller

    # Order processing (feature/order-processing). Documents are private files (upload_dir/private).
    max_document_mb: int = 10            # voucher / ticket / policy / client's evidence, each
    max_documents_per_order: int = 20
    max_cancel_evidence_files: int = 5   # form 4.6.1.3, field 4
    # Trips end -> «Завершено» the day after end_date in this time zone (ТЗ table 4.1).
    business_timezone: str = "Europe/Kyiv"
    # How often the server completes finished trips; 0 turns the loop off (tests).
    order_completion_interval_sec: int = 3600

    # Reviews (form 4.6.1.4, field 6): photos are private files, served only for published
    # reviews (or to the author / managers).
    max_review_photos: int = 10
    max_review_photo_mb: int = 5


settings = Settings()
