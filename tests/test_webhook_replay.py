from backend.ingest.webhook_replay import select_recent_replay_row


def test_select_recent_replay_row_ignores_retryable_error_and_degraded_rows():
    rows = [
        {"id": "degraded", "processing_status": "degraded"},
        {"id": "error", "processing_status": "error"},
        {"id": "empty", "processing_status": ""},
    ]

    assert select_recent_replay_row(rows) is None


def test_select_recent_replay_row_blocks_pending_processing_and_processed_rows():
    for status in ["pending", "processing", "processed"]:
        row = {"id": f"row-{status}", "processing_status": status}
        assert select_recent_replay_row([row]) == row


def test_select_recent_replay_row_returns_first_blocking_row_in_order():
    rows = [
        {"id": "error", "processing_status": "error"},
        {"id": "processed", "processing_status": "processed"},
        {"id": "pending", "processing_status": "pending"},
    ]

    assert select_recent_replay_row(rows)["id"] == "processed"


def test_select_recent_replay_row_is_case_insensitive():
    row = {"id": "mixed", "processing_status": "Processing"}

    assert select_recent_replay_row([row]) == row
