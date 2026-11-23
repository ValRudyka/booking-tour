"""Test setup: migrate the TEST database to head, give each test a session that is rolled back."""
import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _TestSettings(BaseSettings):
    """Reads TEST_DATABASE_URL from the environment or backend/.env (like app.config does)."""
    model_config = SettingsConfigDict(env_file=os.path.join(BACKEND_DIR, ".env"),
                                      env_file_encoding="utf-8", extra="ignore")
    test_database_url: str = "postgresql+psycopg://tour_app:change_me@localhost:5432/tour_website_test"


TEST_DATABASE_URL = _TestSettings().test_database_url
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    command.downgrade(cfg, "base")   # start from an empty schema every run
    command.upgrade(cfg, "head")
    eng = create_engine(TEST_DATABASE_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def client(db):
    """HTTP client whose requests use the test session (everything is rolled back after the test)."""
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def db(engine) -> Iterator[Session]:
    """Each test runs inside a transaction that is rolled back afterwards."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
