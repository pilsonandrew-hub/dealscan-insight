"""Transport cost calculation based on distance bands."""
import functools
import os
import yaml


_CONFIGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


@functools.lru_cache(maxsize=1)
def _load_rates():
    with open(os.path.join(_CONFIGS_DIR, "transit_rates.yml")) as f:
        return yaml.safe_load(f)


@functools.lru_cache(maxsize=1)
def _load_state_miles():
    with open(os.path.join(_CONFIGS_DIR, "state_miles_to_ca.yml")) as f:
        return yaml.safe_load(f).get("miles", {})


def calc_transport_cost(state: str, rates_cfg: dict = None, miles_cfg: dict = None) -> float:
    """Return estimated transport cost from `state` to CA."""
    if rates_cfg is None:
        rates_cfg = _load_rates()
    if miles_cfg is None:
        miles_cfg = _load_state_miles()

    dist = miles_cfg.get(state, 1000)
    bands = rates_cfg.get("mileage_bands", [])
    band = next((b for b in bands if dist <= b["max_miles"]), bands[-1] if bands else None)
    if band is None:
        cost = dist * 1.8  # fallback rate
    else:
        cost = dist * band["rate_per_mile"]
    return max(350.0, cost)  # minimum charge $350
