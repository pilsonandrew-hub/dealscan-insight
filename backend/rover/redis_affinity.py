"""
Redis-backed affinity vector tracking for Rover personalization.

Key patterns (HSET schema — migrated from flat keys):
  rover:affinity:{user_id}              → HASH with fields per dimension + _last_decay_ts
  rover:last_event:{user_id}            → unix timestamp (float)
  rover:last_updated:{user_id}          → unix timestamp (float)
  rover:active_users                    → SET of user_ids

Decay: half-life of 72 hours, applied lazily on read/write.
TTL: 30 days on all per-user keys.

Migration: if old flat keys (rover:affinity:{user_id}:*) exist, they are
migrated to the new HSET format automatically on first access.
"""
import os
import math
import logging
import time

logger = logging.getLogger(__name__)

DECAY_HALF_LIFE_HOURS = 72
DECAY_FACTOR = math.exp(-math.log(2) / DECAY_HALF_LIFE_HOURS)  # per hour
KEY_TTL = 2592000  # 30 days in seconds

# Internal hash field name for tracking last decay timestamp
_DECAY_TS_FIELD = "_last_decay_ts"

# Affinity dimension weights by event type (multiplicative on base weight)
_DIMENSION_EVENT_SCALE = {
    "view": 0.2,
    "click": 1.0,
    "save": 3.0,
    "bid": 5.0,
    "purchase": 8.0,
}


def get_redis_client():
    """Return a Redis client or None if REDIS_URL is not configured."""
    url = os.getenv("REDIS_PRIVATE_URL") or os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis
        client = redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"[ROVER] Redis unavailable: {e}")
        return None


def _hash_key(user_id: str) -> str:
    """HSET key for user affinity (new schema)."""
    return f"rover:affinity:{user_id}"


def _flat_key_prefix(user_id: str) -> str:
    """Prefix used by the old flat key schema."""
    return f"rover:affinity:{user_id}:"


def _dedup_key(user_id: str, event_type: str, item_id: str) -> str:
    return f"rover:dedup:{user_id}:{event_type}:{item_id}"


def is_duplicate_event(redis_client, user_id: str, event_type: str, item_id: str, ttl_seconds: int = 300) -> bool:
    """
    Returns True if this user+event+item combo was seen within the last ttl_seconds.
    Uses Redis SETNX so the first caller wins — subsequent identical events are deduped.
    ttl defaults to 5 minutes (view events) — callers may pass shorter for high-weight events.
    """
    if not item_id:
        return False
    key = _dedup_key(user_id, event_type, item_id)
    set_result = redis_client.set(key, 1, nx=True, ex=ttl_seconds)
    # set returns None if key already existed (NX condition failed) → duplicate
    return set_result is None


def _last_event_key(user_id: str) -> str:
    return f"rover:last_event:{user_id}"


def _last_updated_key(user_id: str) -> str:
    return f"rover:last_updated:{user_id}"


def _price_bracket(price: float) -> str:
    if price < 10_000:
        return "low"
    elif price < 25_000:
        return "mid"
    else:
        return "premium"


def _get_first(item_data: dict, *keys: str):
    for key in keys:
        value = item_data.get(key)
        if value not in (None, ""):
            return value
    return None


def _extract_dimensions(item_data: dict) -> list[str]:
    """Extract affinity dimension strings from top-level or nested item payloads."""
    dims = []

    data = item_data or {}
    item = data.get("item", data)

    make = str(_get_first(item, "make") or _get_first(data, "make") or "").lower().strip()
    model = str(_get_first(item, "model") or _get_first(data, "model") or "").lower().strip()
    segment = str(
        _get_first(item, "segment_tier", "segmentTier", "segment")
        or _get_first(data, "segment_tier", "segmentTier", "segment")
        or ""
    ).strip().lower()
    source = str(
        _get_first(item, "source_site", "sourceSite", "source")
        or _get_first(data, "source_site", "sourceSite", "source")
        or ""
    ).lower().strip()

    price_raw = _get_first(
        item,
        "current_bid",
        "currentBid",
        "buy_now_price",
        "buyNowPrice",
        "price",
        "estimated_sale_price",
        "estimatedSalePrice",
    ) or _get_first(
        data,
        "current_bid",
        "currentBid",
        "buy_now_price",
        "buyNowPrice",
        "price",
        "estimated_sale_price",
        "estimatedSalePrice",
    ) or 0
    try:
        price = float(price_raw)
    except (TypeError, ValueError):
        price = 0.0

    if make:
        dims.append(f"make:{make}")
    if make and model:
        dims.append(f"model:{make}:{model}")
    if segment:
        dims.append(f"segment:{segment}")
    if source:
        dims.append(f"source:{source}")
    if price > 0:
        dims.append(f"price_range:{_price_bracket(price)}")

    return dims


# ---------------------------------------------------------------------------
# Migration helper
# ---------------------------------------------------------------------------

def migrate_to_hset(redis_client, user_id: str) -> bool:
    """
    Migrate old flat keys ``rover:affinity:{user_id}:*`` into the new HSET
    format (``rover:affinity:{user_id}`` hash).

    Returns True if migration was performed (old keys existed), False otherwise.
    Called lazily on first access per user — safe to call multiple times.
    """
    prefix = _flat_key_prefix(user_id)
    pattern = f"{prefix}*"
    hash_key = _hash_key(user_id)

    old_keys: list[str] = []
    cursor = 0
    while True:
        cursor, keys = redis_client.scan(cursor, match=pattern, count=100)
        old_keys.extend(keys)
        if cursor == 0:
            break

    if not old_keys:
        return False

    logger.info(f"[ROVER] Migrating {len(old_keys)} flat affinity keys to HSET for user {user_id}")

    pipeline = redis_client.pipeline()
    for key in old_keys:
        val = redis_client.get(key)
        if val is not None:
            dim = key[len(prefix):]
            try:
                pipeline.hset(hash_key, dim, float(val))
            except (TypeError, ValueError):
                pass
        pipeline.delete(key)

    pipeline.expire(hash_key, KEY_TTL)
    pipeline.execute()
    return True


# ---------------------------------------------------------------------------
# Core affinity functions
# ---------------------------------------------------------------------------

def apply_decay(redis_client, user_id: str) -> None:
    """
    Apply time-based decay lazily to the affinity hash for a user.

    Instead of scanning flat keys on every write (old O(n) approach), decay is
    stored as a timestamp field ``_last_decay_ts`` inside the hash itself and
    applied on the next read or write — making this O(1) metadata + O(d) for
    d dimensions only when decay is actually meaningful.
    """
    hash_key = _hash_key(user_id)

    # Pull all fields including the internal decay timestamp
    raw = redis_client.hgetall(hash_key)
    if not raw:
        return

    last_decay_ts = raw.get(_DECAY_TS_FIELD)
    now_ts = time.time()

    if last_decay_ts is None:
        # First time — just stamp it, no decay to apply yet
        redis_client.hset(hash_key, _DECAY_TS_FIELD, now_ts)
        return

    try:
        hours_elapsed = (now_ts - float(last_decay_ts)) / 3600.0
    except (TypeError, ValueError):
        return

    if hours_elapsed <= 0:
        return

    decay = DECAY_FACTOR ** hours_elapsed
    if decay >= 0.9999:
        return  # not worth rewriting

    pipeline = redis_client.pipeline()
    for field, val in raw.items():
        if field == _DECAY_TS_FIELD:
            continue
        try:
            new_val = float(val) * decay
            pipeline.hset(hash_key, field, new_val)
        except (TypeError, ValueError):
            pass

    pipeline.hset(hash_key, _DECAY_TS_FIELD, now_ts)
    pipeline.expire(hash_key, KEY_TTL)
    pipeline.execute()


def increment_affinity(
    redis_client,
    user_id: str,
    item_data: dict,
    event_type: str,
    weight: float,
) -> None:
    """
    Apply time-decay then increment affinity dimensions for this event.
    Non-fatal: exceptions are logged and swallowed by the caller.

    Migrates old flat keys to HSET format on first call if they exist.
    """
    hash_key = _hash_key(user_id)

    # Lazy migration from old flat-key schema
    # Only attempt if the new hash doesn't already exist
    if not redis_client.exists(hash_key):
        migrate_to_hset(redis_client, user_id)

    # Apply decay before writing new signal
    apply_decay(redis_client, user_id)

    dims = _extract_dimensions(item_data)
    if not dims:
        return

    now_ts = time.time()
    pipeline = redis_client.pipeline()

    for dim in dims:
        pipeline.hincrbyfloat(hash_key, dim, weight)

    # Stamp decay timestamp if not present (apply_decay may have set it already,
    # but hsetnx ensures we don't overwrite a freshly-set value)
    pipeline.hsetnx(hash_key, _DECAY_TS_FIELD, now_ts)
    pipeline.expire(hash_key, KEY_TTL)

    # Update last-event / last-updated timestamps
    last_key = _last_event_key(user_id)
    last_updated_key = _last_updated_key(user_id)
    pipeline.set(last_key, now_ts, ex=KEY_TTL)
    pipeline.set(last_updated_key, now_ts, ex=KEY_TTL)
    pipeline.sadd("rover:active_users", user_id)
    pipeline.execute()


def get_affinity_vector(redis_client, user_id: str) -> dict[str, float]:
    """
    Return ``{dimension: score}`` dict for the user. Empty dict if no data.

    Applies lazy decay on read, migrates old flat keys if needed.
    """
    hash_key = _hash_key(user_id)

    # Lazy migration from old flat-key schema
    if not redis_client.exists(hash_key):
        migrate_to_hset(redis_client, user_id)

    # Apply decay before returning scores
    apply_decay(redis_client, user_id)

    raw = redis_client.hgetall(hash_key)
    if not raw:
        return {}

    result: dict[str, float] = {}
    for field, val in raw.items():
        if field == _DECAY_TS_FIELD:
            continue
        try:
            result[field] = float(val)
        except (TypeError, ValueError):
            pass

    return result
