"""FastAPI entry point. Run: uvicorn app.main:app --reload (from the backend folder)."""
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers import auth

app = FastAPI(
    title="Tour website API",
    description="REST API туристичного вебсайту (курсовий проєкт).",
    version="0.2.0",
)

app.include_router(auth.router, prefix="/api")


@app.get("/health", tags=["service"], summary="Перевірка стану сервісу та БД")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
