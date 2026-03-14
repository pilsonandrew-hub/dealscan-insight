"""
Redis-backed affinity vector tracking for Rover personalization.

Key patterns:
  rover:affinity:{user_id}:{dimension}  → float score (HSET field per dimension)
  rover:last_event:{user_id}            → unix timestamp (float)
  rover:last_updated:{user_id}          → unix timestamp (float)
  rover:active_users                    → SET of user_ids

Decay: half-life of 72 hours applied on each write.
TTL: 30 days on all per-user keys.
"""
import os
import math
import logging
import time

logger = logging.getLogger(__name__)

DECAY_HALF_LIFE_HOURS = 72
DECAY_FACTOR = math.exp(-math.log(2) / DECAY_HALF_LIFE_HOURS)  # per hour
KEY_TTL = 2592000  # 30 days in seconds

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


def _affinity_key(user_id: str, dimension: str) -> str:
    return f"rover:affinity:{user_id}:{dimension}"


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
    """Extract affinity dimension strings from item_data."""
    dims = []

    make = str(_get_first(item_data, "make") or "").lower().strip()
    model = str(_get_first(item_data, "model") or "").lower().strip()
    segment = str(_get_first(item_data, "segment_tier", "segmentTier", "segment") or "").strip().lower()
    source = str(_get_first(item_data, "source_site", "sourceSite", "source") or "").lower().strip()

    price_raw = _get_first(
        item_data,
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


def apply_decay(redis_client, user_id: str) -> None:
    """Apply time-based decay to all affinity dimensions for a user."""
    last_key = _last_event_key(user_id)
    last_ts = redis_client.get(last_key)
    if last_ts is None:
        return

    try:
        hours_elapsed = (time.time() - float(last_ts)) / 3600.0
    except (TypeError, ValueError):
        return

    if hours_elapsed <= 0:
        return

    decay = DECAY_FACTOR ** hours_elapsed
    if decay >= 0.9999:
        return  # not worth rewriting

    pattern = f"rover:affinity:{user_id}:*"
    cursor = 0
    pipeline = redis_client.pipeline()
    found_any = False

    while True:
        cursor, keys = redis_client.scan(cursor, match=pattern, count=100)
        for key in keys:
            val = redis_client.get(key)
            if val is not None:
                try:
                    new_val = float(val) * decay
                    pipeline.set(key, new_val, ex=KEY_TTL)
                    found_any = True
                except (TypeError, ValueError):
                    pass
        if cursor == 0:
            break

    if found_any:
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
    """
    # Apply decay before writing new signal
    apply_decay(redis_client, user_id)

    dims = _extract_dimensions(item_data)
    if not dims:
        return

    pipeline = redis_client.pipeline()
    for dim in dims:
        key = _affinity_key(user_id, dim)
        pipeline.incrbyfloat(key, weight)
        pipeline.expire(key, KEY_TTL)

    # Update last-event timestamp
    now_ts = time.time()
    last_key = _last_event_key(user_id)
    last_updated_key = _last_updated_key(user_id)
    pipeline.set(last_key, now_ts, ex=KEY_TTL)
    pipeline.set(last_updated_key, now_ts, ex=KEY_TTL)
    pipeline.sadd("rover:active_users", user_id)
    pipeline.execute()


def get_affinity_vector(redis_client, user_id: str) -> dict[str, float]:
    """Return {dimension: score} dict for the user. Empty dict if no data."""
    pattern = f"rover:affinity:{user_id}:*"
    prefix = f"rover:affinity:{user_id}:"
    last_updated_ts = redis_client.get(_last_updated_key(user_id)) or redis_client.get(_last_event_key(user_id))
    decay = 1.0
    if last_updated_ts is not None:
        try:
            hours_elapsed = max(0.0, (time.time() - float(last_updated_ts)) / 3600.0)
            decay = DECAY_FACTOR ** hours_elapsed
        except (TypeError, ValueError):
            decay = 1.0
    result: dict[str, float] = {}

    cursor = 0
    while True:
        cursor, keys = redis_client.scan(cursor, match=pattern, count=100)
        for key in keys:
            val = redis_client.get(key)
            if val is not None:
                try:
                    dim = key[len(prefix):]
                    result[dim] = float(val) * decay
                except (TypeError, ValueError):
                    pass
        if cursor == 0:
            break

    return result
