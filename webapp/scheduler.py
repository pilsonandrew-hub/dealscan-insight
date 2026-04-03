"""Internal APScheduler — SniperScope only.

GovDeals scraping is handled exclusively by Apify actors (ds-govdeals, ds-govdeals-sold).
The internal Playwright-based scrapers are disabled: Railway containers do not have
Playwright browser binaries installed and Apify already covers GovDeals on a 3hr schedule.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


def start_scheduler():
    """Start the internal scheduler — SniperScope check only."""
    from webapp.routers.sniper import _run_sniper_check_internal

    # SniperScope check every 5 minutes
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
    logger.info("[SCHEDULER] GovDeals scrapers disabled — handled by Apify actors")


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[SCHEDULER] Shutdown complete")
