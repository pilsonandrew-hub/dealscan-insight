"""Condition grade proxy — infer vehicle condition from available metadata."""

import re

# Tier ladder: Poor < Fair < Good < Excellent
_TIERS = ["Poor", "Fair", "Good", "Excellent"]

_DAMAGE_SIGNALS = (
    "flood", "fire", "hail", "storm", "water damage", "salvage",
    "frame damage", "structural damage", "rollover", "totaled",
)

_NO_START_SIGNALS = (
    "no start", "not running", "does not run", "non-runner",
    "non runner", "will not start", "won't start",
)

_RUNS_DRIVES_SIGNALS = (
    "runs and drives", "starts and runs", "runs great", "drives great",
    "runs well", "drives well", "runs fine",
)


def _tier_index(grade: str) -> int:
    try:
        return _TIERS.index(grade)
    except ValueError:
        return _TIERS.index("Fair")


def _clamp(index: int) -> str:
    return _TIERS[max(0, min(len(_TIERS) - 1, index))]


def _grade_to_score(grade: str) -> float:
    return float(_tier_index(grade))


def _score_to_grade(score: float) -> str:
    bounded = max(0.0, min(float(len(_TIERS) - 1), float(score)))
    if bounded >= 2.5:
        return "Excellent"
    if bounded >= 1.5:
        return "Good"
    if bounded >= 0.5:
        return "Fair"
    return "Poor"


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
    3. "runs and drives"/"starts and runs" → upgrade one tier
    4. Age-based baseline (0-1yr: Excellent, 2-3yr: Good, 4-6yr: Fair, 7+yr: Poor)
    5. Mileage adjustment (<30k: no penalty, 30k-60k: -0.5, 60k-90k: -1, 90k+: -2)
    6. Parse condition codes like "Grade 3" or "Condition 2" in description
    7. Default: "Fair"
    """
    from datetime import datetime
    current_year = datetime.utcnow().year

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

    runs_drives_bump = any(signal in text for signal in _RUNS_DRIVES_SIGNALS)

    # 6. Parse explicit condition/grade codes from description (check early,
    #    but apply after baseline so code takes precedence over heuristics)
    code_grade = None
    code_match = re.search(
        r'\b(?:grade|condition)\s+([1-5])\b',
        description.lower()
    )
    if code_match:
        code_num = int(code_match.group(1))
        code_grade = {
            5: "Excellent",
            4: "Good",
            3: "Fair",
            2: "Poor",
            1: "Poor",
        }[code_num]

    if code_grade is not None:
        score = _grade_to_score(code_grade)
        if runs_drives_bump:
            score += 1.0
        return _score_to_grade(score)

    # 4. Age-based baseline
    if year and year > 1900:
        age = current_year - year
        if age <= 1:
            base_grade = "Excellent"
        elif age <= 3:
            base_grade = "Good"
        elif age <= 6:
            base_grade = "Fair"
        else:
            base_grade = "Poor"
    else:
        base_grade = "Fair"

    score = _grade_to_score(base_grade)

    # 5. Mileage adjustment
    if mileage:
        if 30000 <= mileage < 60000:
            score -= 0.5
        elif 60000 <= mileage < 90000:
            score -= 1.0
        elif mileage >= 90000:
            score -= 2.0

    # 3. "Runs and drives" bump
    if runs_drives_bump:
        score += 1.0

    return _score_to_grade(score)
