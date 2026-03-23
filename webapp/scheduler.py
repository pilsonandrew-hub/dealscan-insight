"""Internal APScheduler — replaces GitHub Actions cron for SniperScope."""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def start_scheduler():
    """Start the internal scheduler with SniperScope check job."""
    from webapp.routers.sniper import _run_sniper_check_internal

    scheduler.add_job(
        _run_sniper_check_internal,
        trigger="interval",
        minutes=5,
        id="sniper_check",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    logger.info("[SCHEDULER] SniperScope check scheduled every 5 minutes")


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[SCHEDULER] Shutdown complete")
