"""
Rover Heuristic Scorer
Scores deals based on user preference vectors with mileage/price buckets.
Algorithm from Rover SPEC-01 v1.2
"""
from typing import Dict, Any
import math

# Event weights for preference building
EVENT_WEIGHTS = {
    "view": 0.2,
    "click": 1.0,
    "save": 3.0,
    "bid": 5.0,
    "purchase": 8.0,
}

DECAY_HALF_LIFE_MS = 72 * 60 * 60 * 1000  # 72 hours

# Mileage buckets
MILEAGE_BUCKETS = [15000, 30000, 60000, 100000]

# Price buckets
PRICE_BUCKETS = [10000, 20000, 35000, 50000]


def mileage_bucket(mileage: float) -> str:
    if mileage < 15000: return "0-15k"
    elif mileage < 30000: return "15-30k"
    elif mileage < 60000: return "30-60k"
    elif mileage < 100000: return "60-100k"
    else: return "100k+"


def price_bucket(price: float) -> str:
    if price < 10000: return "sub-10k"
    elif price < 20000: return "10-20k"
    elif price < 35000: return "20-35k"
    elif price < 50000: return "35-50k"
    else: return "50k+"


def apply_decay(weight: float, event_ts_ms: float, now_ms: float, half_life_ms: float = DECAY_HALF_LIFE_MS) -> float:
    """Apply exponential decay: w * exp(-lambda * delta_t)"""
    lam = math.log(2) / half_life_ms
    delta = max(0, now_ms - event_ts_ms)
    return weight * math.exp(-lam * delta)


def build_preference_vector(events: list, now_ms: float) -> Dict[str, float]:
    """
    Build user preference vector from event history.
    Returns dict of {dimension: affinity_score}
    """
    prefs: Dict[str, float] = {}

    for event in events:
        raw_weight = EVENT_WEIGHTS.get(event.get("event_type", "view"), 0.2)
        ts = event.get("timestamp_ms", now_ms)
        weight = apply_decay(raw_weight, ts, now_ms)

        item = event.get("item_data", {})

        dims = {
            f"make:{item.get('make', '')}": weight,
            f"model:{item.get('model', '')}": weight,
            f"body:{item.get('bodyType', '')}": weight * 0.7,
            f"source:{item.get('source', '')}": weight * 0.5,
            f"state:{item.get('state', '')}": weight * 0.6,
            f"mileage_bucket:{mileage_bucket(item.get('mileage', 50000))}": weight * 0.8,
            f"price_bucket:{price_bucket(item.get('price', 25000))}": weight * 0.9,
        }

        for dim, val in dims.items():
            prefs[dim] = prefs.get(dim, 0) + val

    return prefs


def score_item(prefs: Dict[str, float], item: Dict[str, Any]) -> float:
    """
    Score a single deal item against user preference vector.
    Returns float score (higher = better match).
    """
    score = 0.0

    # Make/model/body affinity
    score += prefs.get(f"make:{item.get('make', '')}", 0)
    score += prefs.get(f"model:{item.get('model', '')}", 0)
    # Support both camelCase (event item_data) and snake_case (DB opportunity rows)
    body = item.get('body_type') or item.get('bodyType') or ''
    score += prefs.get(f"body:{body}", 0) * 0.7
    score += prefs.get(f"source:{item.get('source_site') or item.get('source', '')}", 0) * 0.5
    score += prefs.get(f"state:{item.get('state', '')}", 0) * 0.6
    score += prefs.get(f"mileage_bucket:{mileage_bucket(item.get('mileage', 50000))}", 0) * 0.8
    # Opportunity rows use current_bid, not price
    _price = item.get('current_bid') or item.get('price') or item.get('estimated_sale_price') or 25000
    score += prefs.get(f"price_bucket:{price_bucket(_price)}", 0) * 0.9

    # Under-MMR bonus (key arbitrage signal)
    mmr = item.get("mmr", 0)
    price = item.get("price", 0)
    if mmr and price and price < mmr:
        under_mmr_pct = (mmr - price) / mmr
        score += under_mmr_pct * 10  # Up to 10 bonus points

    # DOS score integration
    dos = item.get("dos_score", item.get("arbitrage_score", 0))
    score += (dos / 100) * 5  # Up to 5 bonus points

    return round(score, 4)


def rank_opportunities(prefs: Dict[str, float], opportunities: list, top_n: int = 25) -> list:
    """
    Rank a list of opportunities by preference score.
    Returns top_n items with _score field added.
    """
    if not prefs:
        # Cold start: rank by DOS score only
        ranked = sorted(opportunities, key=lambda x: x.get("dos_score", x.get("arbitrage_score", 0)), reverse=True)
        for i, item in enumerate(ranked):
            item["_score"] = max(0, 1.0 - (i * 0.02))
        return ranked[:top_n]

    scored = []
    for item in opportunities:
        s = score_item(prefs, item)
        scored.append({**item, "_score": s})

    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored[:top_n]
