"""FastAPI application entrypoint with lifespan management."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router as api_router
from core.config import settings
from core.logging import logger, setup_logging
from db.connection import initialize_schema
from scheduler import build_scheduler

BASE_DIR = Path(__file__).resolve().parent
scheduler = build_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and graceful shutdown lifespan management."""
    setup_logging()
    logger.info("Starting Algo Stock Scanner application...")
    initialize_schema()
    scheduler.start()
    yield
    logger.info("Shutting down Algo Stock Scanner application...")
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Algo Stock Scanner — RSI & RB Knoxville Divergence",
    description="Enterprise-grade Indian Equity Scanner with Lookback Screening and Next-Candle Confirmation.",
    version="2.0.0",
    lifespan=lifespan,
)

# Static and UI routes
app.mount("/static", StaticFiles(directory=BASE_DIR / "frontend"), name="static")
app.include_router(api_router)


@app.get("/", include_in_schema=False)
def serve_dashboard() -> FileResponse:
    """Serve single-page frontend application."""
    return FileResponse(BASE_DIR / "frontend" / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=False,
    )
