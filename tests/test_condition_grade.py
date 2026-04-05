"""Unit tests for condition grade proxy."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.ingest.condition import compute_condition_grade

import datetime as _dt
CURRENT_YEAR = _dt.datetime.now(_dt.timezone.utc).year


def test_flood_damage_type_is_poor():
    assert compute_condition_grade(damage_type="flood damage") == "Poor"


def test_fire_damage_type_is_poor():
    assert compute_condition_grade(damage_type="fire") == "Poor"


def test_no_start_description_is_poor():
    assert compute_condition_grade(description="Vehicle does not run, no start condition.") == "Poor"


def test_not_running_description_is_poor():
    assert compute_condition_grade(description="This unit is not running.") == "Poor"


def test_runs_and_drives_bumps_fair_to_good():
    # Fair baseline (old year, average mileage), plus "runs and drives" → Good
    result = compute_condition_grade(
        description="Runs and drives fine.",
        year=CURRENT_YEAR - 3,
        mileage=25000,
    )
    assert result == "Good"


def test_age_baseline_new_vehicle_is_excellent():
    result = compute_condition_grade(year=CURRENT_YEAR, mileage=20000)
    assert result == "Excellent"


def test_age_baseline_2yr_is_good():
    result = compute_condition_grade(year=CURRENT_YEAR - 2, mileage=25000)
    assert result == "Good"


def test_low_mileage_bumps_grade():
    # 3-year-old = Fair baseline, <15k mileage = +1 → Good
    result = compute_condition_grade(year=CURRENT_YEAR - 3, mileage=10000)
    assert result == "Good"


def test_high_mileage_lowers_grade():
    # 2-year-old = Good baseline, 40k mileage = -1 → Fair
    result = compute_condition_grade(year=CURRENT_YEAR - 2, mileage=40000)
    assert result == "Fair"


def test_grade_code_5_is_excellent():
    assert compute_condition_grade(description="Grade 5 unit, well maintained.") == "Excellent"


def test_grade_code_2_is_poor():
    assert compute_condition_grade(description="Condition 2 vehicle, needs work.") == "Poor"


def test_grade_code_3_is_fair():
    assert compute_condition_grade(description="Grade 3 overall condition.") == "Fair"


def test_grade_code_with_runs_and_drives_bump():
    # Grade 3 = Fair, runs and drives bump → Good
    result = compute_condition_grade(
        description="Grade 3 vehicle. Runs and drives well."
    )
    assert result == "Good"


def test_default_no_info_is_fair():
    assert compute_condition_grade() == "Fair"
