"""Condition grade proxy — infer vehicle condition from available metadata."""

_DAMAGE_SIGNALS = (
    "flood", "fire", "hail", "storm", "water damage", "salvage",
    "frame damage", "structural damage", "rollover", "totaled",
)

_NO_START_SIGNALS = (
    "no start", "not running", "does not run", "non-runner",
    "non runner", "will not start", "won't start",
)

def compute_condition_grade(
    title: str = "",
    description: str = "",
    mileage: int = 0,
    year: int = 0,
    damage_type: str = "",
) -> str:
    """
    Infer condition grade from available data.
    Returns one of: "Excellent", "Good", "Fair", "Poor", "Unknown"

    Priority order:
    1. damage_type signals → "Poor" immediately
    2. Explicit "no start"/"not running" in description → "Poor"
    3. Age-based baseline (0-1yr: Excellent, 2-3yr: Good, 4-6yr: Fair, 7+yr: Poor)
    4. Mileage adjustment (<60k: no penalty, 60k-90k: -1, 90k+: -2)
    5. Default: "Fair"
    """
    text = f"{title} {description} {damage_type}".lower()

    # 1. Damage type signals → Poor immediately
    if damage_type:
        for signal in _DAMAGE_SIGNALS:
            if signal in damage_type.lower():
                return "Poor"

    # 2. "No start" / "not running" in any text → Poor immediately
    for signal in _NO_START_SIGNALS:
        if signal in text:
            return "Poor"

    # Also check damage signals in title/description
    for signal in _DAMAGE_SIGNALS:
        if signal in text:
            return "Poor"

    # Audit #4: use the fixed 2026 thresholds with whole-step mileage penalties.
    if year and year > 1900:
        age = 2026 - year
        if age <= 1:
            base_score = 4
        elif age <= 3:
            base_score = 3
        elif age <= 6:
            base_score = 2
        else:
            base_score = 1
    else:
        base_score = 2

    if mileage:
        if mileage >= 90000:
            base_score -= 2
        elif mileage >= 60000:
            base_score -= 1
        elif mileage >= 30000:
            pass

    base_score = max(1, base_score)
    grades = {4: "Excellent", 3: "Good", 2: "Fair", 1: "Poor"}
    return grades[base_score]
