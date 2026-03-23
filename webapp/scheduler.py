"""Internal APScheduler — replaces GitHub Actions cron for SniperScope."""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def start_scheduler():
    """Start the internal scheduler with SniperScope check and GovDeals scrapers."""
    from webapp.routers.sniper import _run_sniper_check_internal
    from backend.scrapers.govdeals_sold import run_govdeals_sold_scraper
    from backend.scrapers.govdeals_active import run_govdeals_active_scraper

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

    # GovDeals active scraper every 3 hours (offset by 15 min from sold scraper)
    scheduler.add_job(
        run_govdeals_active_scraper,
        trigger="cron",
        hour="0,3,6,9,12,15,18,21",
        minute=15,
        id="govdeals_active_scraper",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("[SCHEDULER] SniperScope check scheduled every 5 minutes")
    logger.info("[SCHEDULER] GovDeals sold scraper scheduled daily at 2am UTC")
    logger.info("[SCHEDULER] GovDeals active scraper scheduled every 3 hours at :15")


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[SCHEDULER] Shutdown complete")
