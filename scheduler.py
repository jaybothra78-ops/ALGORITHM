"""Scheduled background job execution with APScheduler."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from core.logging import logger
from services.scanner import ScannerEngine


def build_scheduler() -> BackgroundScheduler:
    """Build and configure the scheduled market scanner."""
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    
    # Run daily scan at 15:45 IST (Market Close)
    scheduler.add_job(
        func=lambda: ScannerEngine.run_daily_scan("ALL"),
        trigger=CronTrigger(hour=15, minute=45, timezone="Asia/Kolkata"),
        id="daily_market_close_scan",
        replace_existing=True,
    )
    logger.info("Scheduler configured: Daily scan at 15:45 IST.")
    return scheduler
