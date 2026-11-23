"""Application settings, read from environment variables or the backend/.env file."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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


settings = Settings()
