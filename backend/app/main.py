import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.db.session import async_session_factory, engine
from app.integrations.manager import PrinterListenerManager
from app.services.auto_pause import auto_pause_manager
from app.ws.redis_listener import redis_listener


# Without this the root logger stays at WARNING and the listeners' layer/job transitions
# (logged at INFO) never reach the container log.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    listener_task = asyncio.create_task(redis_listener(app.state.redis))

    app.state.printer_manager = PrinterListenerManager(async_session_factory, app.state.redis)
    await app.state.printer_manager.start_all_existing()

    yield

    await auto_pause_manager.cancel_all()
    await app.state.printer_manager.stop_all()
    listener_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await listener_task
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(title="Deteccion Impresion 3D", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins.split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    # The web (another origin: Vite on :5173) reads how old a camera snapshot is.
    expose_headers=["X-Frame-Age-Seconds"],
)

app.include_router(api_v1_router)


@app.get("/health")
async def health() -> dict:
    db_ok = True
    redis_ok = True

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    try:
        await app.state.redis.ping()
    except Exception:
        redis_ok = False

    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }
