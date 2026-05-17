import hashlib

from backend.ingest.canonical_identity import (
    compute_canonical_id,
    normalize_make_for_identity,
    normalize_model_for_identity,
)


def test_normalize_make_for_identity_preserves_legacy_aliases():
    assert normalize_make_for_identity("Chevy") == "chevrolet"
    assert normalize_make_for_identity("Mercedes-Benz") == "mercedes"
    assert normalize_make_for_identity("VW") == "volkswagen"
    assert normalize_make_for_identity(" Ford ") == "ford"


def test_normalize_model_for_identity_uses_first_two_words_and_strips_punctuation():
    assert normalize_model_for_identity("F-150 SuperCrew 4x4") == "f150 supercrew"
    assert normalize_model_for_identity(" Silverado 1500 Crew Cab ") == "silverado 1500"


def test_compute_canonical_id_prefers_valid_vin():
    vin = "1HGCM82633A004352"
    vehicle = {"vin": vin, "listing_url": "https://example.com/lot/123"}

    assert compute_canonical_id(vehicle) == hashlib.sha256(vin.encode()).hexdigest()[:32]


def test_compute_canonical_id_uses_listing_url_when_vin_missing():
    url = "https://example.com/lot/123"
    vehicle = {"vin": "", "listing_url": url}

    assert compute_canonical_id(vehicle) == hashlib.sha256(url.encode()).hexdigest()[:32]


def test_compute_canonical_id_uses_legacy_bucket_key_fallback():
    vehicle = {
        "year": 2023,
        "make": "Chevy",
        "model": "Silverado 1500 Crew Cab",
        "state": "ca",
        "mileage": 37499,
    }
    expected_key = "2023_chevrolet_silverado 1500_CA_37500"

    assert compute_canonical_id(vehicle) == hashlib.sha256(expected_key.encode()).hexdigest()[:32]
