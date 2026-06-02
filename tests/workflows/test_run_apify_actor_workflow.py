from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "run-apify-actor.yml"


def test_run_apify_actor_workflow_supports_bounded_govdeals_proof():
    text = WORKFLOW.read_text()

    assert "ds-govdeals" in text
    assert "CuKaIAcWyFS0EPrAz" in text
    assert "max_pages" in text
    assert "runtime_budget_ms" in text
    assert '"maxPages": int(os.environ.get("MAX_PAGES") or "1")' in text
    assert '"runtimeBudgetMs": int(os.environ.get("RUNTIME_BUDGET_MS") or "240000")' in text
    assert "pushed_rows_with_description" in text
    assert "pushed_rows_with_detail_text" in text
    assert "description_samples" in text
    assert "source_quality_proof" in text
