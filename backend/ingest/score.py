"""Deal scoring: computes margin and opportunity score for auction listings."""
import os
import yaml

from .transport import calc_transport_cost

_CONFIGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


def _load_fees():
    with open(os.path.join(_CONFIGS_DIR, "fees.yml")) as f:
        return yaml.safe_load(f).get("sites", {})


def score_deal(
    bid: float,
    mmr_ca: float,
    state: str,
    source_site: str,
    fees_cfg: dict = None,
    rates_cfg: dict = None,
    miles_cfg: dict = None,
) -> dict:
    """
    Compute deal margin and score.

    Returns a dict with:
        premium      - buyer's premium amount
        doc_fee      - documentation fee
        transport    - estimated transport cost
        total_cost   - bid + all fees + transport
        margin       - mmr_ca - total_cost
        score        - margin / max(1000, bid)
    """
    if fees_cfg is None:
        fees_cfg = _load_fees()

    site_fees = fees_cfg.get(source_site, {"buyers_premium_pct": 10.0, "doc_fee": 50})
    premium = bid * site_fees.get("buyers_premium_pct", 10.0) / 100.0
    doc_fee = site_fees.get("doc_fee", 50)
    transport = calc_transport_cost(state, rates_cfg=rates_cfg, miles_cfg=miles_cfg)
    total_cost = bid + premium + doc_fee + transport
    margin = mmr_ca - total_cost
    score = margin / max(1000.0, bid)

    return {
        "premium": round(premium, 2),
        "doc_fee": doc_fee,
        "transport": round(transport, 2),
        "total_cost": round(total_cost, 2),
        "margin": round(margin, 2),
        "score": round(score, 4),
    }
