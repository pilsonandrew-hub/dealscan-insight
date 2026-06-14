import pytest
import inspect
from fastapi import HTTPException

from webapp.routers import lifecycle


def test_expire_endpoint_requires_secret(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "lifecycle-secret")
    with pytest.raises(HTTPException) as exc:
        lifecycle._verify_lifecycle_secret(None)
    assert exc.value.status_code == 401


def test_expire_endpoint_accepts_secret(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "lifecycle-secret")
    lifecycle._verify_lifecycle_secret("lifecycle-secret")


def test_expire_endpoint_uses_constant_time_secret_comparison():
    source = inspect.getsource(lifecycle._verify_lifecycle_secret)

    assert "compare_digest" in source
    assert ".strip() != expected" not in source
