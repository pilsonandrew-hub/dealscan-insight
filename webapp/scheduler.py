"""Internal APScheduler — replaces GitHub Actions cron for SniperScope."""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def start_scheduler():
    """Start the internal scheduler with SniperScope check and GovDeals sold scraper."""
    from webapp.routers.sniper import _run_sniper_check_internal
    from backend.scrapers.govdeals_sold import run_govdeals_sold_scraper

    # SniperScope check every 5 minutes
    scheduler.add_job(
        _run_sniper_check_internal,
        trigger="interval",
        minutes=5,
        id="sniper_check",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # GovDeals sold scraper daily at 2am UTC
    scheduler.add_job(
        run_govdeals_sold_scraper,
        trigger="cron",
        hour=2,
        minute=0,
        id="govdeals_sold_scraper",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("[SCHEDULER] SniperScope check scheduled every 5 minutes")
    logger.info("[SCHEDULER] GovDeals sold scraper scheduled daily at 2am UTC")


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[SCHEDULER] Shutdown complete")
