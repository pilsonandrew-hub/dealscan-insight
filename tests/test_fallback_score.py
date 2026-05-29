from backend.ingest.fallback_score import build_fallback_score


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


def test_build_fallback_score_keeps_invalid_mileage_untrusted_even_when_score_is_high():
    for mileage in (None, 0, -1, "", "  ", "unknown", "0", "-2", "0.0", "-0.1", "-2.5", "nan", "NaN", "inf", "-inf"):
        result = build_fallback_score({
            "title": "2024 Toyota Camry",
            "make": "Toyota",
            "year": 2024,
            "current_bid": 500,
            "state": "CA",
            "source_site": "govdeals",
            "mileage": mileage,
        })

        assert result["score"] >= 80
        assert result["score_provenance"]["input_profile"]["has_mileage"] is False
        assert result["investment_grade"] is None
        assert result["ceiling_pass"] is False
        assert result["max_bid"] == 0
