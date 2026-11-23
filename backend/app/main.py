"""FastAPI entry point. Run: uvicorn app.main:app --reload (from the backend folder)."""
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.routers import auth, catalog, manager_tours, orders, reference

app = FastAPI(
    title="Tour website API",
    description="REST API туристичного вебсайту (курсовий проєкт).",
    version="0.3.0",
)

app.include_router(auth.router, prefix="/api")
app.include_router(manager_tours.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(reference.router, prefix="/api")
app.include_router(orders.router, prefix="/api")

# Only tour photos are public. Mounting the whole upload_dir would also publish anything stored
# there later (order documents, passports), so private files live outside uploads/tours and are
# downloaded only through endpoints that check the user's rights.
# StaticFiles refuses to start if the folder is missing, so create it first.
TOUR_PHOTOS_DIR = Path(settings.upload_dir) / "tours"
TOUR_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/tours", StaticFiles(directory=TOUR_PHOTOS_DIR), name="tour-photos")


@app.get("/health", tags=["service"], summary="Перевірка стану сервісу та БД")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
