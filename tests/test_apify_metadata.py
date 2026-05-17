from datetime import timezone

from backend.ingest.apify_metadata import extract_apify_webhook_metadata


def test_extract_apify_webhook_metadata_prefers_resource_fields():
    payload = {
        "source": "apify-webhook",
        "itemCount": "9",
        "actorRunId": "payload-run",
        "defaultDatasetId": "payload-dataset",
        "resource": {
            "actId": "actor-resource",
            "id": "run-resource",
            "defaultDatasetId": "dataset-resource",
            "itemCount": "12",
            "startedAt": "2026-05-17T12:34:56.000Z",
        },
        "eventData": {
            "actorId": "actor-event",
            "resource": {
                "id": "run-nested",
                "defaultDatasetId": "dataset-nested",
                "itemCount": 15,
            },
        },
    }

    metadata = extract_apify_webhook_metadata(payload)

    assert metadata["source"] == "apify-webhook"
    assert metadata["actor_id"] == "actor-resource"
    assert metadata["run_id"] == "run-resource"
    assert metadata["dataset_id"] == "dataset-resource"
    assert metadata["item_count"] == 9
    assert metadata["created_at"].tzinfo == timezone.utc
    assert metadata["created_at"].isoformat() == "2026-05-17T12:34:56+00:00"


def test_extract_apify_webhook_metadata_uses_nested_event_data_when_resource_missing():
    payload = {
        "eventData": {
            "actorId": "actor-event",
            "actorRunId": "run-event",
            "defaultDatasetId": "dataset-event",
            "itemCount": "7",
            "createdAt": "2026-05-17T01:02:03Z",
        }
    }

    metadata = extract_apify_webhook_metadata(payload)

    assert metadata["source"] == "apify"
    assert metadata["actor_id"] == "actor-event"
    assert metadata["run_id"] == "run-event"
    assert metadata["dataset_id"] == "dataset-event"
    assert metadata["item_count"] == 7
    assert metadata["created_at"].isoformat() == "2026-05-17T01:02:03+00:00"


def test_extract_apify_webhook_metadata_counts_inline_items_and_ignores_invalid_count():
    metadata = extract_apify_webhook_metadata({"itemCount": "bad", "items": [{}, {}, {}]})
    assert metadata["item_count"] is None

    metadata = extract_apify_webhook_metadata({"items": [{}, {}, {}]})
    assert metadata["item_count"] == 3


def test_extract_apify_webhook_metadata_handles_non_dict_payload():
    metadata = extract_apify_webhook_metadata("not-a-dict")
    assert metadata == {
        "source": "apify",
        "actor_id": None,
        "run_id": None,
        "dataset_id": None,
        "item_count": None,
        "created_at": None,
    }
