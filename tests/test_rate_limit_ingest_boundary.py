import asyncio
import importlib
import os
import sys
import types
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class _BaseHTTPMiddleware:
    def __init__(self, app):
        self.app = app


class _JSONResponse:
    def __init__(self, content, status_code=200, headers=None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}


class _State:
    pass


class _Request:
    def __init__(self, path, headers=None, client_host="127.0.0.1", user_id=None):
        self.url = types.SimpleNamespace(path=path)
        self.headers = headers or {}
        self.client = types.SimpleNamespace(host=client_host)
        self.state = _State()
        if user_id is not None:
            self.state.user = types.SimpleNamespace(id=user_id)


class _FakePipeline:
    def __init__(self, *, incr_count=1, execute_error=None):
        self._ops = []
        self._incr_count = incr_count
        self._execute_error = execute_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def incr(self, key):
        self._ops.append(("incr", key))

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))

    async def execute(self):
        if self._execute_error is not None:
            raise self._execute_error
        results = []
        for op in self._ops:
            if op[0] == "incr":
                results.append(self._incr_count)
            else:
                results.append(True)
        return results


class _FakeRedisClient:
    def __init__(self, *, ping_error=None, pipeline_incr_count=1, pipeline_error=None):
        self._ping_error = ping_error
        self._pipeline_incr_count = pipeline_incr_count
        self._pipeline_error = pipeline_error
        self.logged = []

    async def ping(self):
        if self._ping_error is not None:
            raise self._ping_error
        return True

    def pipeline(self):
        return _FakePipeline(
            incr_count=self._pipeline_incr_count,
            execute_error=self._pipeline_error,
        )

    async def lpush(self, key, value):
        self.logged.append((key, value))

    async def ltrim(self, key, start, stop):
        self.logged.append((key, start, stop))

    async def mget(self, keys):
        return ["0" for _ in keys]


starlette_module = types.ModuleType("starlette")
starlette_middleware_module = types.ModuleType("starlette.middleware")
starlette_middleware_base = types.ModuleType("starlette.middleware.base")
starlette_middleware_base.BaseHTTPMiddleware = _BaseHTTPMiddleware
starlette_requests = types.ModuleType("starlette.requests")
starlette_requests.Request = object
starlette_responses = types.ModuleType("starlette.responses")
starlette_responses.JSONResponse = _JSONResponse
sys.modules.setdefault("starlette", starlette_module)
sys.modules.setdefault("starlette.middleware", starlette_middleware_module)
sys.modules.setdefault("starlette.middleware.base", starlette_middleware_base)
sys.modules.setdefault("starlette.requests", starlette_requests)
sys.modules.setdefault("starlette.responses", starlette_responses)

redis_module = types.ModuleType("redis")
redis_asyncio_module = types.ModuleType("redis.asyncio")
redis_asyncio_module.from_url = lambda *args, **kwargs: _FakeRedisClient()
redis_module.asyncio = redis_asyncio_module
sys.modules.setdefault("redis", redis_module)
sys.modules.setdefault("redis.asyncio", redis_asyncio_module)

settings_obj = types.SimpleNamespace(
    redis_url="redis://example.test:6379/0",
    rate_limit_requests=100,
    rate_limit_window_seconds=60,
    rate_limit_ingest_requests=10,
    rate_limit_ingest_window_seconds=60,
    rate_limit_trust_proxy_headers=False,
    rate_limit_trusted_proxy_cidrs="127.0.0.1/32,::1/128",
)
config_package = types.ModuleType("config")
config_package.__path__ = [os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config"))]
config_settings_module = types.ModuleType("config.settings")
config_settings_module.settings = settings_obj
sys.modules.setdefault("config", config_package)
sys.modules.setdefault("config.settings", config_settings_module)

rate_limit = importlib.import_module("webapp.middleware.rate_limit")


class RateLimitIngestBoundaryTests(unittest.TestCase):
    def setUp(self):
        settings_obj.rate_limit_requests = 100
        settings_obj.rate_limit_window_seconds = 60
        settings_obj.rate_limit_ingest_requests = 10
        settings_obj.rate_limit_ingest_window_seconds = 60
        settings_obj.rate_limit_trust_proxy_headers = False
        settings_obj.rate_limit_trusted_proxy_cidrs = "127.0.0.1/32,::1/128"

    def test_extract_client_ip_ignores_spoofed_forwarded_headers_from_untrusted_peer(self):
        settings_obj.rate_limit_trust_proxy_headers = True
        settings_obj.rate_limit_trusted_proxy_cidrs = "10.0.0.0/8"
        request = _Request(
            "/api/ingest/apify",
            headers={"x-forwarded-for": "198.51.100.10"},
            client_host="203.0.113.25",
        )

        self.assertEqual(rate_limit.extract_client_ip(request), "203.0.113.25")

    def test_extract_client_ip_uses_leftmost_untrusted_hop_from_trusted_proxy_chain(self):
        settings_obj.rate_limit_trust_proxy_headers = True
        settings_obj.rate_limit_trusted_proxy_cidrs = "10.0.0.0/8,203.0.113.5/32"
        request = _Request(
            "/api/ingest/apify",
            headers={"x-forwarded-for": "198.51.100.10, 203.0.113.5"},
            client_host="10.1.2.3",
        )

        self.assertEqual(rate_limit.extract_client_ip(request), "198.51.100.10")

    def test_ingest_dispatch_fails_closed_when_redis_init_fails(self):
        redis_client = _FakeRedisClient(ping_error=RuntimeError("redis down"))
        rate_limit.redis.from_url = lambda *args, **kwargs: redis_client
        middleware = rate_limit.RateLimitMiddleware(app=None)
        request = _Request("/api/ingest/apify", client_host="127.0.0.1")
        call_next_called = False

        async def call_next(_request):
            nonlocal call_next_called
            call_next_called = True
            return "next"

        response = asyncio.run(middleware.dispatch(request, call_next))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content["error"], "Ingest rate limit unavailable")
        self.assertFalse(call_next_called)

    def test_generic_route_still_fails_open_when_redis_init_fails(self):
        redis_client = _FakeRedisClient(ping_error=RuntimeError("redis down"))
        rate_limit.redis.from_url = lambda *args, **kwargs: redis_client
        middleware = rate_limit.RateLimitMiddleware(app=None)
        request = _Request("/api/vehicles", client_host="127.0.0.1")

        async def call_next(_request):
            return "next"

        response = asyncio.run(middleware.dispatch(request, call_next))

        self.assertEqual(response, "next")

    def test_ingest_route_limit_is_stricter_than_generic_api(self):
        rate_limit.redis.from_url = lambda *args, **kwargs: _FakeRedisClient(pipeline_incr_count=11)
        ingest_middleware = rate_limit.RateLimitMiddleware(app=None)
        ingest_request = _Request("/api/ingest/apify", client_host="127.0.0.1")

        async def call_next(_request):
            return "next"

        ingest_response = asyncio.run(ingest_middleware.dispatch(ingest_request, call_next))
        self.assertEqual(ingest_response.status_code, 429)
        self.assertEqual(ingest_response.headers["Retry-After"], "60")

        rate_limit.redis.from_url = lambda *args, **kwargs: _FakeRedisClient(pipeline_incr_count=11)
        generic_middleware = rate_limit.RateLimitMiddleware(app=None)
        generic_request = _Request("/api/vehicles", client_host="127.0.0.1")
        generic_response = asyncio.run(generic_middleware.dispatch(generic_request, call_next))

        self.assertEqual(generic_response, "next")

    def test_ingest_dispatch_fails_closed_when_redis_check_fails(self):
        rate_limit.redis.from_url = lambda *args, **kwargs: _FakeRedisClient(
            pipeline_error=RuntimeError("redis execute failed")
        )
        middleware = rate_limit.RateLimitMiddleware(app=None)
        request = _Request("/api/ingest/apify", client_host="127.0.0.1")

        async def call_next(_request):
            return "next"

        response = asyncio.run(middleware.dispatch(request, call_next))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content["error"], "Ingest rate limit unavailable")


if __name__ == "__main__":
    unittest.main()
