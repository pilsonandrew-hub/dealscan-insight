from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.main import app


def _routes() -> set[tuple[str, tuple[str, ...]]]:
    return {
        (route.path, tuple(sorted(route.methods or [])))
        for route in app.routes
        if isinstance(route, APIRoute)
    }


def test_outcome_alias_routes_are_mounted_under_api_prefix() -> None:
    routes = _routes()

    assert ("/api/outcomes/summary", ("GET",)) in routes
    assert ("/api/outcomes", ("POST",)) in routes
    assert ("/api/outcomes/{opportunity_id}", ("PATCH",)) in routes
    assert ("/api/outcomes/bid", ("POST",)) in routes


def test_rover_debug_is_internal_only_and_not_in_openapi_schema() -> None:
    schema = app.openapi()

    assert "/api/rover/debug" not in schema.get("paths", {})


def test_legacy_scraper_status_route_exists_for_frontend_contract() -> None:
    assert ("/api/analytics/scraper-status", ("GET",)) in _routes()


def test_outcomes_aliases_return_validation_errors_for_malformed_payloads() -> None:
    client = TestClient(app)

    for method, path in (
        ("post", "/api/outcomes"),
        ("post", "/api/outcomes/bid"),
        ("patch", "/api/outcomes/example-opportunity"),
    ):
        response = getattr(client, method)(path, json={})
        assert response.status_code == 422
