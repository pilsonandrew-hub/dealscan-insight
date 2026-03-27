"""
config_loader.py
────────────────
Reads integration env vars from Supabase app_config table as fallback
when Railway environment variables are not set.

Priority: os.environ → Supabase app_config → None

Usage:
    from backend.ingest.config_loader import get_config

    token = get_config("NOTION_TOKEN")
    key   = get_config("OPENROUTER_API_KEY")
"""

import os
import logging
import httpx
from typing import Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lbnxzvqppccajllsqaaw.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SERVICE_ROLE_KEY_REDACTED"
)

_config_cache: dict[str, str] = {}
_cache_loaded = False


def _load_from_supabase() -> dict[str, str]:
    """Fetch all rows from app_config table."""
    global _cache_loaded
    try:
        response = httpx.get(
            f"{SUPABASE_URL}/rest/v1/app_config?select=key,value",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
            timeout=5.0,
        )
        if response.status_code == 200:
            rows = response.json()
            config = {r["key"]: r["value"] for r in rows if "key" in r and "value" in r}
            logger.info(f"[ConfigLoader] Loaded {len(config)} keys from Supabase app_config")
            _cache_loaded = True
            return config
        else:
            logger.warning(f"[ConfigLoader] Supabase app_config fetch failed: HTTP {response.status_code}")
    except Exception as e:
        logger.warning(f"[ConfigLoader] Could not load app_config from Supabase: {e}")
    return {}


def get_config(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a config value. Checks:
    1. os.environ (Railway env vars — highest priority)
    2. Supabase app_config table (fallback)
    3. default

    Args:
        key: The environment variable / config key name.
        default: Value to return if not found anywhere.
    """
    global _config_cache, _cache_loaded

    # 1. Check os.environ first
    val = os.getenv(key, "").strip()
    if val:
        return val

    # 2. Load from Supabase if not cached yet
    if not _cache_loaded:
        _config_cache = _load_from_supabase()

    val = _config_cache.get(key, "").strip()
    if val:
        logger.debug(f"[ConfigLoader] {key} resolved from Supabase app_config")
        return val

    return default


def reload_config() -> None:
    """Force reload from Supabase (clears cache)."""
    global _config_cache, _cache_loaded
    _cache_loaded = False
    _config_cache = {}
    _config_cache = _load_from_supabase()
