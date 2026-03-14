import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.ingest.score import score_deal
from webapp.routers.ingest import passes_basic_gates, score_vehicle


def test_passes_basic_gates_rejects_title_brand_keywords():
    vehicle = {
        "title": "2024 Toyota Camry Salvage Title",
        "title_status": "clean",
        "vin": "4T1C11AK0RU000001",
        "make": "Toyota",
        "model": "Camry",
        "current_bid": 10000,
        "state": "CA",
        "year": 2024,
        "mileage": 25000,
        "listing_url": "https://example.com/vehicle/1",
        "source_site": "govdeals",
    }

    result = passes_basic_gates(vehicle)

    assert result["pass"] is False
    assert result["reason"] == "title_brand_rejected (title matched 'salvage')"


def test_passes_basic_gates_checks_vin_for_title_brand_keywords():
    vehicle = {
        "title": "2024 Honda Accord",
        "vin": "FLOOD123456789XYZ",
        "make": "Honda",
        "model": "Accord",
        "current_bid": 10000,
        "state": "CA",
        "year": 2024,
        "mileage": 15000,
        "listing_url": "https://example.com/vehicle/2",
        "source_site": "govdeals",
    }

    result = passes_basic_gates(vehicle)

    assert result["pass"] is False
    assert result["reason"] == "title_brand_rejected (vin matched 'flood')"


def test_score_deal_subtracts_recon_reserve_from_margin():
    result = score_deal(
        bid=10000,
        mmr_ca=20000,
        state="CA",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=2024,
        mileage=50000,
        fees_cfg={"GovDeals": {"buyers_premium_pct": 10.0, "doc_fee": 50}},
        rates_cfg={"mileage_bands": [{"max_miles": 5000, "rate_per_mile": 1.0}]},
        miles_cfg={"CA": 100},
    )

    assert result["recon_reserve"] == 650.0
    assert result["transport"] == 350.0
    assert result["total_cost"] == 12050.0
    assert result["margin"] == 7950.0


def test_score_vehicle_adds_police_fleet_recon_buffer():
    vehicle = {
        "title": "2023 Ford Explorer Police Interceptor Utility",
        "agency_name": "City Fleet Services",
        "vin": "1FM5K8AR5PGA00001",
        "make": "Ford",
        "model": "Explorer Interceptor",
        "current_bid": 10000,
        "state": "CA",
        "year": 2023,
        "mileage": 50000,
        "listing_url": "https://example.com/vehicle/3",
        "source_site": "govdeals",
    }

    result = score_vehicle(vehicle)

    assert result["recon_reserve"] == 950.0
