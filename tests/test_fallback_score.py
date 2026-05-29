import math

from backend.ingest.fallback_score import build_fallback_score


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


def test_build_fallback_score_marks_severe_provenance_and_preserves_payload_shape():
    result = build_fallback_score({
        "title": "2023 Toyota Camry",
        "make": "Toyota",
        "year": 2023,
        "current_bid": 10000,
        "state": "CA",
        "source_site": "govdeals",
    })

    assert result["score_version"] == "fallback_v1"
    assert result["score_engine_impl"] == "webapp.routers.ingest._fallback_score"
    assert result["assumption_level"] == "severe"
    assert result["fallback_flags"] == ["hard_fallback_score", "no_mmr"]
    assert result["score_provenance"]["lane"] == "fallback"
    assert result["score_provenance"]["input_profile"]["has_bid"] is True
    assert result["score_provenance"]["input_profile"]["source_site"] == "govdeals"
    assert result["ceiling_pass"] is False
    assert result["ceiling_reason"] == "fallback_score"
    assert result["expected_close_source"] == "fallback_current_bid_only"


def test_build_fallback_score_records_missing_bid_in_profile_and_basis():
    result = build_fallback_score({"title": "Unknown", "make": "", "year": 2000, "state": "CA"})

    assert result["score_provenance"]["input_profile"]["has_bid"] is False
    assert result["expected_close_bid"] == 0
    assert result["acquisition_price_basis"] == 0


def test_build_fallback_score_keeps_invalid_mileage_untrusted_with_zero_raw_score():
    for mileage in INVALID_MILEAGE_VALUES:
        result = build_fallback_score({
            "title": "2024 Toyota Camry",
            "make": "Toyota",
            "year": 2024,
            "current_bid": 500,
            "state": "CA",
            "source_site": "govdeals",
            "mileage": mileage,
        })

        assert result["score"] == 0.0
        assert result["dos_score"] == 0.0
        assert result["legacy_dos_score"] == 0.0
        assert result["score_provenance"]["input_profile"]["has_mileage"] is False
        assert result["investment_grade"] is None
        assert result["ceiling_pass"] is False
        assert result["max_bid"] == 0

    missing_result = build_fallback_score({
        "title": "2024 Toyota Camry",
        "make": "Toyota",
        "year": 2024,
        "current_bid": 500,
        "state": "CA",
        "source_site": "govdeals",
    })
    assert missing_result["score"] == 0.0
    assert missing_result["dos_score"] == 0.0
    assert missing_result["score_provenance"]["input_profile"]["has_mileage"] is False
    assert missing_result["ceiling_pass"] is False
    assert missing_result["max_bid"] == 0

def test_build_fallback_score_preserves_valid_mileage_profile_without_trust_surface():
    result = build_fallback_score({
        "title": "2024 Toyota Camry",
        "make": "Toyota",
        "year": 2024,
        "current_bid": 500,
        "state": "CA",
        "source_site": "govdeals",
        "mileage": 12000,
    })

    assert result["score"] > 0.0
    assert result["dos_score"] == result["score"]
    assert result["legacy_dos_score"] == result["score"]
    assert result["score_provenance"]["input_profile"]["has_mileage"] is True
    assert result["investment_grade"] is None
    assert result["ceiling_pass"] is False
    assert result["max_bid"] == 0
    assert result["assumption_level"] == "severe"
    assert result["fallback_flags"] == ["hard_fallback_score", "no_mmr"]

