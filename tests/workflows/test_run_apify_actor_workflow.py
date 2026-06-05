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


def test_run_apify_actor_workflow_supports_manual_jjkane_proof():
    text = WORKFLOW.read_text()

    assert "ds-jjkane" in text
    assert "lvb7T6VMFfNUQpqlq" in text
    assert "JJ_KANE_MAX_ITEMS" in text
    assert '"maxItems": int(os.environ.get("JJ_KANE_MAX_ITEMS") or "75")' in text


def test_run_apify_actor_workflow_supports_bounded_govplanet_proof():
    text = WORKFLOW.read_text()

    assert "ds-govplanet" in text
    assert "pO2t5UDoSVmO1gvKJ" in text
    assert "GOVPLANET_MAX_ITEMS_PER_CATEGORY" in text
    assert "GOVPLANET_MAX_DETAIL_PAGES" in text
    assert '"maxItemsPerCategory": int(os.environ.get("GOVPLANET_MAX_ITEMS_PER_CATEGORY") or "1")' in text
    assert '"maxDetailPages": int(os.environ.get("GOVPLANET_MAX_DETAIL_PAGES") or "1")' in text


def test_run_apify_actor_workflow_supports_bounded_hibid_v2_proof():
    text = WORKFLOW.read_text()

    assert "ds-hibid-v2" in text
    assert "7s9e0eATTt1kuGGfE" in text
    assert "HIBID_MAX_PAGES" in text
    assert "HIBID_MAX_MILEAGE" in text
    assert "HIBID_MIN_YEAR" in text
    assert '"maxPages": int(os.environ.get("HIBID_MAX_PAGES") or "1")' in text
    assert '"maxMileage": int(os.environ.get("HIBID_MAX_MILEAGE") or "50000")' in text
    assert '"minYear": int(os.environ.get("HIBID_MIN_YEAR") or str(datetime.now(timezone.utc).year - 4))' in text
