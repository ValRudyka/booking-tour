"""FastAPI entry point. Run: uvicorn app.main:app --reload (from the backend folder)."""
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.routers import (auth, catalog, finance, manager_orders, manager_tours, notifications, orders,
                         passports, payments, reference)
from app.services.order_expiry import run_expiry_job

logger = logging.getLogger("tour.orders")


async def expiry_loop(interval_sec: float) -> None:
    """Cancel orders with expired seat holds every `interval_sec` seconds.
    The job is synchronous (SQLAlchemy sync), so it runs in a worker thread and does not block
    the event loop; an error is logged and the loop goes on."""
    while True:
        try:
            count = await asyncio.to_thread(run_expiry_job)
            if count:
                logger.info("Cancelled %d order(s) with an expired seat hold", count)
        except Exception:
            logger.exception("Order expiry job failed")
        await asyncio.sleep(interval_sec)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: start the expiry loop (unless ORDER_EXPIRY_INTERVAL_SEC=0). Shutdown: stop it."""
    task = None
    if settings.order_expiry_interval_sec > 0:
        task = asyncio.create_task(expiry_loop(settings.order_expiry_interval_sec))
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="Tour website API",
    description="REST API туристичного вебсайту (курсовий проєкт).",
    version="0.4.0",
    lifespan=lifespan,
)

app.include_router(auth.router, prefix="/api")
app.include_router(manager_tours.router, prefix="/api")
app.include_router(manager_orders.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(reference.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(passports.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(finance.router, prefix="/api")
app.include_router(finance.orders_router, prefix="/api")
app.include_router(notifications.router, prefix="/api")

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
