from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "internal-pipeline-truth-check.yml"


def test_internal_pipeline_truth_workflow_prints_gate_aggregates():
    text = WORKFLOW.read_text()

    assert "workflow_dispatch:" in text
    assert "opportunity_id:" in text
    assert "active_dos_score_buckets_sample" in text
    assert "active_gate_breakdown_sample" in text
    assert "active_pricing_maturity_counts_sample" in text
    assert "active_source_counts_sample" in text
    assert "active_dos80_gate_blocker_counts_sample" in text
    assert "active_dos80_alert_eligible_sample" in text
    assert "active_dos80_condition_counts_sample" in text
    assert "active_dos80_condition_blocker_basis_counts_sample" in text
    assert "active_dos80_condition_blocker_basis_by_source_sample" in text
    assert "active_dos80_condition_blocker_basis_samples" in text
    assert "active_dos80_condition_storage_gap_count_sample" in text
    assert "active_dos80_condition_storage_gap_by_source_sample" in text
    assert "active_dos80_condition_storage_gap_samples" in text
    assert "active_dos80_pricing_maturity_counts_sample" in text
    assert '"pricing_substrate": truth.get("pricing_substrate")' in text
    assert "/api/internal/opportunity-condition-proof/" in text
    assert "condition_evidence_fields" in text
    assert "source_identity" in text
    assert "condition_backfill_assessment" in text


def test_internal_pipeline_truth_workflow_can_trace_recovered_source_evidence():
    text = WORKFLOW.read_text()

    assert "Trace recovered source condition evidence" in text
    assert "APIFY_TOKEN: ${{ secrets.APIFY_TOKEN }}" in text
    assert "scripts/trace_condition_source_evidence.py" in text
    assert "--condition-proof-json /tmp/opportunity-condition-proof.json" in text
    assert "--run-id" in text
    assert "source_condition_trace" in text
