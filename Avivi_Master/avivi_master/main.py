from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from avivi_master.init_db import init_models
from avivi_master.jobs.roi_nightly import run_nightly_roi_job
from avivi_master.routers import admin, commands, enroll, events, heartbeat, missions, relay
from avivi_master.telegram_master import start_master_bot_thread
from avivi_master.config import settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    await init_models()
    log.info("Database ready")
    start_master_bot_thread()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_nightly_roi_job,
        "cron",
        hour=settings.nightly_roi_hour_utc,
        minute=0,
        id="roi_nightly",
        replace_existing=True,
    )
    scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Avivi Master", lifespan=lifespan)
app.include_router(enroll.router)
app.include_router(heartbeat.router)
app.include_router(missions.router)
app.include_router(commands.router)
app.include_router(events.router)
app.include_router(relay.router)
app.include_router(admin.router)


@app.get("/health")
async def health() -> dict:
    from datetime import datetime

    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}
