"""FastAPI entry point. Run: uvicorn app.main:app --reload (from the backend folder)."""
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.routers import auth, manager_tours

app = FastAPI(
    title="Tour website API",
    description="REST API туристичного вебсайту (курсовий проєкт).",
    version="0.3.0",
)

app.include_router(auth.router, prefix="/api")
app.include_router(manager_tours.router, prefix="/api")

# Uploaded photos. StaticFiles refuses to start if the folder is missing, so create it first.
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/health", tags=["service"], summary="Перевірка стану сервісу та БД")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
