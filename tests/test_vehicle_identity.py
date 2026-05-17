from datetime import datetime

from backend.ingest.vehicle_identity import (
    estimate_mmr,
    estimate_mmr_details,
    extract_make,
    extract_model,
    extract_year,
)


def test_extract_year_accepts_current_era_vehicle_years():
    assert extract_year("2024 Toyota Camry SE") == 2024
    assert extract_year("1989 Ford Bronco") is None
    assert extract_year(f"{datetime.now().year + 2} Toyota Camry") is None


def test_extract_make_and_model_use_known_patterns_before_fallback():
    title = "2024 Ford F150 SuperCrew XLT"
    make = extract_make(title)

    assert make == "Ford"
    assert extract_model(title, make) == "F-150"


def test_extract_model_falls_back_to_words_after_year_and_make():
    assert extract_model("2022 Lucid Air Grand Touring", "Lucid") == "Air Grand"


def test_estimate_mmr_details_prefers_model_then_make_then_segment_fallbacks():
    assert estimate_mmr_details("Toyota", "Camry") == {
        "mmr": 22000.0,
        "basis": "model:camry",
        "confidence_proxy": 90.0,
    }
    assert estimate_mmr_details("Toyota", "Unknown") == {
        "mmr": 24000.0,
        "basis": "make:toyota",
        "confidence_proxy": 72.0,
    }
    assert estimate_mmr_details("UnknownMake", "UnknownModel") == {
        "mmr": 15000.0,
        "basis": "segment:sedan_other",
        "confidence_proxy": 45.0,
    }


def test_estimate_mmr_keeps_legacy_numeric_facade():
    assert estimate_mmr("Toyota", "Camry") == 22000.0
