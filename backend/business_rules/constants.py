"""Business-critical constants — do not duplicate elsewhere in the repo."""

from __future__ import annotations

# --- Lane bid ceilings (fraction of MMR all-in) ---
PREMIUM_BID_CEILING_PCT = 0.88
STANDARD_BID_CEILING_PCT = 0.80

# --- Lane minimum wholesale gross margin (USD) ---
PREMIUM_MIN_MARGIN = 1500.0
STANDARD_MIN_MARGIN = 2500.0

# --- Lane mileage gates ---
PREMIUM_MAX_MILEAGE = 50_000
STANDARD_MAX_MILEAGE = 100_000
STANDARD_MAX_MILES_PER_YEAR = 18_000

# --- Lane age gates (years back from current calendar year) ---
PREMIUM_VEHICLE_MAX_AGE_YEARS = 4
STANDARD_VEHICLE_MAX_AGE_YEARS = 10

# --- Rust-state hard reject (exception: model year within this many years of current) ---
HIGH_RUST_STATES = frozenset({
    "OH", "MI", "PA", "NY", "WI", "MN", "IL", "IN", "MO", "IA", "ND", "SD", "NE", "KS", "WV",
    "ME", "NH", "VT", "MA", "RI", "CT", "NJ", "MD", "DE",
})
RUST_STATE_NEW_VEHICLE_YEARS = 2

# --- DOS / surface thresholds ---
DOS_SAVE_THRESHOLD = 50.0
ROVER_RECOMMENDATION_THRESHOLD = 65.0
HOT_DEAL_ALERT_THRESHOLD = 80.0

# --- ROI guidance (percent, not ratio) ---
MIN_ROI_HOT_PCT = 20.0
MIN_ROI_GOOD_PCT = 12.0
PLATINUM_MIN_ROI_PER_DAY = 75.0

# --- Alert gating defaults (env may override via alert_thresholds builder) ---
HOT_DEAL_MIN_CONFIDENCE = 55.0
HOT_DEAL_MIN_TRUST_SCORE = 0.25

# Production contract: alerts on unless explicitly disabled in non-prod.
ALERTS_ENABLED_PRODUCTION_DEFAULT = "true"

# Pricing maturity values allowed through hot-alert gate (no proxy).
PRICING_MATURITY_ALERT_ALLOWED = frozenset({"market_comp", "live_market"})

# Proxy-priced deals are blocked from hot alerts unless policy is deliberately relaxed.
PROXY_PRICING_ALERT_ALLOWED = False

# Minimum confidence (0-100 scale) for proxy-priced hot alerts when allowed.
PROXY_ALERT_MIN_CONFIDENCE = 55.0
