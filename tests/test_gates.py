import math

from backend.ingest.gates import (
    find_title_brand_issue,
    is_commercial_hd_tonnage,
    passes_basic_gates,
)


INVALID_MILEAGE_VALUES = (
    None,
    "",
    "  ",
    "unknown",
    0,
    -1,
    "0",
    "-2",
    "0.0",
    "-0.1",
    "-2.5",
    float("nan"),
    math.inf,
    -math.inf,
    "nan",
    "NaN",
    "inf",
    "+inf",
    "-inf",
)


def _tier(year, mileage):
    return "premium"


def _vehicle(**overrides):
    base = {
        "title": "2024 Toyota Camry",
        "vin": "4T1C11AK0RU000001",
        "make": "Toyota",
        "model": "Camry",
        "current_bid": 10000,
        "state": "CA",
        "year": 2024,
        "mileage": 25000,
        "listing_url": "https://example.com/vehicle/1",
    }
    base.update(overrides)
    return base


def test_find_title_brand_issue_preserves_listing_and_vin_matching():
    assert find_title_brand_issue(_vehicle(title="2024 Toyota Camry Salvage Title")) == "title_brand_rejected (listing_text matched 'salvage')"
    assert find_title_brand_issue(_vehicle(title="2024 Toyota Camry", vin="FLOOD123456789XYZ")) == "title_brand_rejected (vin matched 'flood')"


def test_commercial_hd_tonnage_allows_pickup_context_but_rejects_unqualified_2500():
    assert is_commercial_hd_tonnage("Ram 2500 Big Horn") is False
    assert is_commercial_hd_tonnage("Silverado 3500 Crew Cab") is False
    assert is_commercial_hd_tonnage("2500 Cargo Van") is True


def test_passes_basic_gates_rejects_brightdrop_cargo_delivery_vans():
    assert passes_basic_gates(
        _vehicle(
            title="2024 BrightDrop Zevo 400 Base AWD Cargo Delivery Van",
            make="BrightDrop",
            model="Zevo 400",
            state="FL",
            year=2024,
            mileage=10,
        ),
        determine_vehicle_tier=_tier,
    ) == {
        "pass": False,
        "reason": "commercial_vehicle (2024 BrightDrop Zevo 400 Base AWD Cargo Delivery V)",
    }


def test_passes_basic_gates_rejects_detached_truck_beds():
    assert passes_basic_gates(
        _vehicle(
            title="Ford Truck bed",
            make="Ford",
            model="Truck bed",
            current_bid=500,
            state="TN",
            year=2026,
            mileage=1,
            listing_url="https://www.govdeals.com/asset/77/30240",
        ),
        determine_vehicle_tier=_tier,
    ) == {
        "pass": False,
        "reason": "non_vehicle_part (Ford Truck bed)",
    }


def test_passes_basic_gates_preserves_rejection_order_and_reasons():
    assert passes_basic_gates(_vehicle(make="", vin="", title="office chair", current_bid=0), determine_vehicle_tier=_tier) == {
        "pass": False,
        "reason": "not_a_vehicle (no make or valid VIN)",
    }
    assert passes_basic_gates(_vehicle(current_bid=0), determine_vehicle_tier=_tier) == {
        "pass": False,
        "reason": "bid_not_positive ($0)",
    }
    assert passes_basic_gates(_vehicle(state="ON"), determine_vehicle_tier=_tier) == {
        "pass": False,
        "reason": "non_us_state (ON)",
    }


def test_passes_basic_gates_keeps_rust_exception_and_listing_url_gate():
    assert passes_basic_gates(_vehicle(state="OH", year=2021), determine_vehicle_tier=_tier, current_year=2026) == {
        "pass": False,
        "reason": "high_rust_state (OH)",
    }
    assert passes_basic_gates(_vehicle(state="OH", year=2025), determine_vehicle_tier=_tier, current_year=2026) == {
        "pass": True,
        "reason": "ok",
    }
    assert passes_basic_gates(_vehicle(listing_url=""), determine_vehicle_tier=_tier) == {
        "pass": False,
        "reason": "no_listing_url",
    }


def test_passes_basic_gates_uses_injected_tier_result():
    assert passes_basic_gates(_vehicle(), determine_vehicle_tier=lambda year, mileage: "rejected") == {
        "pass": False,
        "reason": "age_or_mileage_exceeded",
    }


def test_passes_basic_gates_rejects_non_positive_mileage_with_canonical_tier():
    from backend.business_rules.gates import determine_vehicle_tier

    for mileage in INVALID_MILEAGE_VALUES:
        assert passes_basic_gates(_vehicle(mileage=mileage), determine_vehicle_tier=determine_vehicle_tier) == {
            "pass": False,
            "reason": "age_or_mileage_exceeded",
        }

    missing_mileage_vehicle = _vehicle()
    missing_mileage_vehicle.pop("mileage")
    assert passes_basic_gates(missing_mileage_vehicle, determine_vehicle_tier=determine_vehicle_tier) == {
        "pass": False,
        "reason": "age_or_mileage_exceeded",
    }
