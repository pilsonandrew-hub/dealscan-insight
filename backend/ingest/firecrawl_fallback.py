"""
firecrawl_fallback.py
─────────────────────
Firecrawl fallback layer for DealerScope scrapers.

Use when:
  - An Apify actor returns empty / 0 results (likely blocked)
  - A listing detail page is Cloudflare-protected or JS-rendered
  - One-off enrichment of a specific auction URL

NOT a replacement for Apify bulk scraping. This is a surgical bypass
for individual blocked pages or enrichment calls.

Usage:
    from backend.ingest.firecrawl_fallback import fetch_page_markdown, is_available

    if is_available():
        md = fetch_page_markdown("https://www.govdeals.com/item/...")
        # md is clean markdown — feed to LLM or parser
"""

import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1/scrape"
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "FIRECRAWL_API_KEY_REDACTED")
TIMEOUT_SECONDS = 30


def is_available() -> bool:
    """Returns True if Firecrawl is configured and ready."""
    return bool(FIRECRAWL_API_KEY and FIRECRAWL_API_KEY.startswith("fc-"))


def fetch_page_markdown(url: str, formats: list[str] | None = None) -> Optional[str]:
    """
    Fetch a URL via Firecrawl and return clean markdown content.

    Args:
        url: The page URL to scrape.
        formats: Output formats. Defaults to ["markdown"].

    Returns:
        Markdown string or None on failure.
    """
    if not is_available():
        logger.warning("[Firecrawl] API key not configured — skipping fallback")
        return None

    formats = formats or ["markdown"]

    try:
        response = httpx.post(
            FIRECRAWL_API_URL,
            headers={
                "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"url": url, "formats": formats},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            logger.warning(f"[Firecrawl] Non-success response for {url}: {data.get('error')}")
            return None

        content = data.get("data", {})
        if isinstance(content, dict):
            md = content.get("markdown", "")
            logger.info(f"[Firecrawl] Fetched {len(md)} chars from {url}")
            return md if md else None

    except httpx.TimeoutException:
        logger.error(f"[Firecrawl] Timeout fetching {url}")
    except httpx.HTTPStatusError as e:
        logger.error(f"[Firecrawl] HTTP {e.response.status_code} for {url}")
    except Exception as e:
        logger.error(f"[Firecrawl] Unexpected error for {url}: {e}")

    return None


def fetch_listing_detail(listing_url: str) -> Optional[dict]:
    """
    Fetch a specific auction listing detail page.
    Returns dict with markdown content and metadata, or None.

    Use this when Apify returns a listing without full description/details.
    """
    md = fetch_page_markdown(listing_url)
    if not md:
        return None

    return {
        "url": listing_url,
        "markdown": md,
        "source": "firecrawl",
        "char_count": len(md),
    }


def try_fallback_scrape(url: str, actor_name: str) -> Optional[str]:
    """
    Convenience wrapper — call when an Apify actor fails on a URL.
    Logs the fallback attempt for SRE visibility.

    Args:
        url: The URL that failed in Apify.
        actor_name: Name of the actor that failed (for logging).

    Returns:
        Markdown content or None.
    """
    logger.warning(f"[Firecrawl] Fallback triggered — actor={actor_name} url={url}")
    result = fetch_page_markdown(url)
    if result:
        logger.info(f"[Firecrawl] Fallback SUCCESS — actor={actor_name} chars={len(result)}")
    else:
        logger.error(f"[Firecrawl] Fallback FAILED — actor={actor_name} url={url}")
    return result
