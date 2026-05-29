import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from webapp.routers import sonar


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def lte(self, *_args, **_kwargs):
        return self

    def or_(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class _Supabase:
    def __init__(self, rows):
        self.rows = rows

    def table(self, _name):
        return _Query(self.rows)


@pytest.fixture(autouse=True)
def isolate_sonar(monkeypatch):
    sonar._memory_store.clear()
    async def no_redis():
        return None

    monkeypatch.setattr(sonar, "_get_redis", no_redis)
    monkeypatch.setattr(sonar, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(sonar, "SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setattr(sonar, "SUPABASE_SERVICE_ROLE_KEY", "service-key")
    yield
    sonar._memory_store.clear()


def test_require_sonar_user_id_rejects_missing_header():
    with pytest.raises(HTTPException) as exc:
        sonar.require_sonar_user_id(None)
    assert exc.value.status_code == 401


def test_require_sonar_user_id_rejects_invalid_token(monkeypatch):
    monkeypatch.setattr(sonar, "_fetch_supabase_user", lambda _token: (_ for _ in ()).throw(HTTPException(status_code=401, detail="Authentication failed")))

    with pytest.raises(HTTPException) as exc:
        sonar.require_sonar_user_id("Bearer bad-token")
    assert exc.value.status_code == 401


def test_require_sonar_user_id_accepts_valid_token(monkeypatch):
    monkeypatch.setattr(sonar, "_fetch_supabase_user", lambda _token: {"id": "user-1"})

    assert sonar.require_sonar_user_id("Bearer valid-token") == "user-1"


def test_supabase_auth_api_key_does_not_fall_back_to_service_role(monkeypatch):
    monkeypatch.setattr(sonar, "SUPABASE_ANON_KEY", None)
    monkeypatch.setattr(sonar, "SUPABASE_SERVICE_ROLE_KEY", "service-key")

    assert sonar._supabase_auth_api_key() == ""


def test_fetch_supabase_user_fails_closed_without_anon_key(monkeypatch):
    monkeypatch.setattr(sonar, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(sonar, "SUPABASE_ANON_KEY", None)
    monkeypatch.setattr(sonar, "SUPABASE_SERVICE_ROLE_KEY", "service-key")

    with pytest.raises(HTTPException) as exc:
        sonar._fetch_supabase_user("token")
    assert exc.value.status_code == 503


def test_sonar_search_requires_auth_before_service_role(monkeypatch):
    called = False

    def _fail_if_called():
        nonlocal called
        called = True
        raise AssertionError("service-role client should not be used without auth")

    monkeypatch.setattr(sonar, "_get_supabase", _fail_if_called)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(sonar.sonar_search(sonar.SearchRequest(query="ford"), authorization=None))
    assert exc.value.status_code == 401
    assert called is False


def test_sonar_search_stores_job_owner(monkeypatch):
    monkeypatch.setattr(sonar, "_fetch_supabase_user", lambda _token: {"id": "user-1"})
    monkeypatch.setattr(
        sonar,
        "_get_supabase",
        lambda: _Supabase([
            {
                "id": "opp-1",
                "title": "2024 Ford F-150",
                "year": 2024,
                "make": "Ford",
                "model": "F-150",
                "current_bid": 10000,
                "source_site": "govdeals",
            }
        ]),
    )

    result = asyncio.run(sonar.sonar_search(sonar.SearchRequest(query="ford"), authorization="Bearer valid"))

    job_id = result["job_id"]
    assert sonar._memory_store[job_id]["user_id"] == "user-1"
    assert result["results"][0]["title"] == "2024 Ford F-150"


def test_sonar_status_rejects_cross_user_job(monkeypatch):
    sonar._memory_store["job-1"] = {
        "job_id": "job-1",
        "user_id": "user-1",
        "status": "complete",
        "results": [],
        "sources": {},
        "timed_out": False,
    }
    monkeypatch.setattr(sonar, "_fetch_supabase_user", lambda _token: {"id": "user-2"})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(sonar.sonar_status("job-1", authorization="Bearer other"))
    assert exc.value.status_code == 403


def test_sonar_status_allows_job_owner(monkeypatch):
    sonar._memory_store["job-1"] = {
        "job_id": "job-1",
        "user_id": "user-1",
        "status": "complete",
        "results": [{"id": "opp-1"}],
        "sources": {"Database": "done"},
        "timed_out": False,
    }
    monkeypatch.setattr(sonar, "_fetch_supabase_user", lambda _token: {"id": "user-1"})

    result = asyncio.run(sonar.sonar_status("job-1", authorization="Bearer valid"))
    assert result["results"] == [{"id": "opp-1"}]
