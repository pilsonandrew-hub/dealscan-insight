def _compute_dos_v2(vehicle: dict, gross_margin: float, condition_grade: Optional[str] = None) -> float:
    margin = _margin_score_v2(gross_margin)
    velocity = _velocity_score_v2(vehicle.get("auction_end_date") or vehicle.get("auction_end_time") or vehicle.get("auction_end"))
    segment = _segment_score_v2(vehicle.get("make",""), vehicle.get("model",""))
    model = _model_score_v2(vehicle.get("make",""), vehicle.get("model",""))
    source = _source_score_v2(vehicle.get("source_site",""))
    condition_adjustments = {"A": 3, "B": 1, "C": 0, "D": -3, "F": -5}
    grade_adjustment = condition_adjustments.get(condition_grade, 0)
    dos = (margin*0.35 + velocity*0.25 + (segment + grade_adjustment)*0.20 + model*0.12 + source*0.08)
    return round(min(100.0, max(0.0, dos)), 1)


def _fallback_score() -> tuple:
    ceiling_pass=False  # Updated to fail safe
    # Additional logic can follow
