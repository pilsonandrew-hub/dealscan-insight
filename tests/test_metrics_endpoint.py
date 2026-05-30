import backend.main as main
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient


ALLOWED_METRIC_KEYS = {"total_requests", "status_codes", "avg_response_time_ms", "health"}


def _client() -> TestClient:
    return TestClient(main.app)


def test_metrics_requires_auth() -> None:
    response = _client().get("/metrics")

    assert response.status_code in (401, 404)
    assert "total_requests" not in response.text


def test_metrics_rejects_wrong_auth(monkeypatch) -> None:
    monkeypatch.setattr(main, "PIPELINE_SECRET", "operator-secret")

    response = _client().get("/metrics", headers={"Authorization": "Bearer wrong"})

    assert response.status_code == 401
    assert "total_requests" not in response.text


def test_metrics_fails_closed_without_pipeline_secret(monkeypatch) -> None:
    monkeypatch.setattr(main, "PIPELINE_SECRET", None)

    response = _client().get("/metrics", headers={"Authorization": "Bearer anything"})

    assert response.status_code == 404
    assert "total_requests" not in response.text


def test_metrics_allows_pipeline_bearer_and_returns_sanitized_payload(monkeypatch) -> None:
    monkeypatch.setattr(main, "PIPELINE_SECRET", "operator-secret")

    response = _client().get("/metrics", headers={"Authorization": "Bearer operator-secret"})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == ALLOWED_METRIC_KEYS
    assert isinstance(payload["total_requests"], int)
    assert isinstance(payload["status_codes"], dict)
    assert isinstance(payload["avg_response_time_ms"], (int, float))
    assert payload["health"] == "healthy"

    serialized = str(payload).lower()
    forbidden_fragments = (
        "secret",
        "token",
        "authorization",
        "bearer",
        "vin",
        "listing_url",
        "webhook",
    )
    assert not any(fragment in serialized for fragment in forbidden_fragments)


def test_metrics_endpoint_is_excluded_from_openapi() -> None:
    schema = main.app.openapi()

    assert "/metrics" not in schema.get("paths", {})


def test_metrics_route_exists_only_on_expected_path() -> None:
    routes = {
        (route.path, tuple(sorted(route.methods or [])))
        for route in main.app.routes
        if isinstance(route, APIRoute)
    }

    assert ("/metrics", ("GET",)) in routes
    assert ("/api/metrics", ("GET",)) not in routes
