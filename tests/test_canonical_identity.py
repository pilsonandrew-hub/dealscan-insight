import hashlib

from backend.ingest.canonical_identity import (
    build_duplicate_recovery_payload,
    compute_canonical_id,
    is_canonical_unique_conflict,
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


def test_build_duplicate_recovery_payload_marks_duplicate_and_updates_new_source():
    row = {
        "id": "new-row",
        "source": "govdeals",
        "all_sources": ["should_be_reset"],
        "duplicate_count": 99,
    }
    canonical_row = {"id": "canonical-1", "all_sources": ["gsa"]}

    duplicate_row, canonical_update = build_duplicate_recovery_payload(row, canonical_row)

    assert duplicate_row["is_duplicate"] is True
    assert duplicate_row["canonical_record_id"] == "canonical-1"
    assert duplicate_row["all_sources"] == []
    assert duplicate_row["duplicate_count"] == 0
    assert canonical_update == {
        "id": "canonical-1",
        "all_sources": ["gsa", "govdeals"],
        "duplicate_count": 1,
    }


def test_build_duplicate_recovery_payload_skips_existing_source_update():
    duplicate_row, canonical_update = build_duplicate_recovery_payload(
        {"source": "gsa"},
        {"id": "canonical-1", "all_sources": ["gsa"]},
    )

    assert duplicate_row["is_duplicate"] is True
    assert canonical_update is None


def test_is_canonical_unique_conflict_matches_legacy_messages():
    assert is_canonical_unique_conflict('duplicate key value violates unique constraint "idx_opportunities_canonical_unique"')
    assert is_canonical_unique_conflict("duplicate key value violates unique constraint on canonical_id and is_duplicate")
    assert not is_canonical_unique_conflict("duplicate key value violates unique constraint on listing_url")
    assert not is_canonical_unique_conflict("")
