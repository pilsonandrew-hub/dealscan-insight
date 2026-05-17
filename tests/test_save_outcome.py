from backend.ingest.save_outcome import mark_save_outcome


def test_mark_save_outcome_records_queryable_score_context():
    vehicle = {
        "score_breakdown": {
            "score_version": "v3_two_lane",
            "score_engine_impl": "score_deal_v3_two_lane",
            "assumption_level": "minor",
            "fallback_flags": ["mmr_proxy_used"],
        }
    }

    outcome = mark_save_outcome(vehicle, "saved_supabase", opportunity_id="opp-123")

    assert vehicle["_save_status"] == "saved_supabase"
    assert vehicle["_save_outcome"] is outcome
    assert outcome["status"] == "saved_supabase"
    assert outcome["opportunity_id"] == "opp-123"
    assert outcome["score_version"] == "v3_two_lane"
    assert outcome["score_engine_impl"] == "score_deal_v3_two_lane"
    assert outcome["score_assumption_level"] == "minor"
    assert outcome["score_fallback_flags"] == ["mmr_proxy_used"]
    assert outcome["recorded_at"]


def test_mark_save_outcome_defaults_missing_fallback_flags_to_empty_list():
    vehicle = {"score_breakdown": {}}

    outcome = mark_save_outcome(vehicle, "below_save_threshold")

    assert outcome["score_fallback_flags"] == []
