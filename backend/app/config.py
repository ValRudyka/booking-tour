"""Application settings, read from environment variables or the backend/.env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://tour_app:change_me@localhost:5432/tour_website"
    sql_echo: bool = False


settings = Settings()
