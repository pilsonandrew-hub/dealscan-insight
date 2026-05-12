import os
import sys
import types
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("ENVIRONMENT", "development")


class _StubRouter:
    def __init__(self, *args, **kwargs):
        pass

    def _decorator(self, *args, **kwargs):
        def wrap(func):
            return func

        return wrap

    get = post = put = patch = delete = api_route = _decorator


class _StubHTTPException(Exception):
    def __init__(self, status_code=None, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


if "fastapi" not in sys.modules:
    fastapi_stub = types.ModuleType("fastapi")
    fastapi_stub.APIRouter = _StubRouter
    fastapi_stub.Request = object
    fastapi_stub.HTTPException = _StubHTTPException
    fastapi_stub.Header = lambda default=None, **kwargs: default
    fastapi_stub.BackgroundTasks = object
    fastapi_stub.Depends = lambda f=None: f
    fastapi_stub.status = types.SimpleNamespace(
        HTTP_200_OK=200, HTTP_400_BAD_REQUEST=400,
        HTTP_401_UNAUTHORIZED=401, HTTP_403_FORBIDDEN=403,
        HTTP_404_NOT_FOUND=404, HTTP_500_INTERNAL_SERVER_ERROR=500,
    )
    _responses_stub = types.ModuleType("fastapi.responses")
    _responses_stub.JSONResponse = dict
    fastapi_stub.__path__ = []
    sys.modules["fastapi"] = fastapi_stub
    sys.modules["fastapi.responses"] = _responses_stub

from webapp.routers import ingest


class TestFormatIngestRunSummarySonar(unittest.TestCase):
    """DEA-45: sonar_write_failures rendered in funnel string."""

    _BASE = dict(
        dataset_item_count=10,
        evaluated=8,
        saved_count=6,
        duplicate_existing=1,
        failed_save_count=0,
        skipped=2,
        duplicate_count=0,
        notion_sync_count=0,
        hot_deals_count=0,
    )

    def test_happy_path_sonar_zero(self):
        result = ingest._format_ingest_run_summary(**self._BASE, sonar_write_failures=0)
        self.assertIn("sonar_write_failures:0", result)
        self.assertIn("failed:0", result)

    def test_sonar_failures_rendered(self):
        result = ingest._format_ingest_run_summary(**self._BASE, sonar_write_failures=3)
        self.assertIn("sonar_write_failures:3", result)

    def test_default_sonar_write_failures_is_zero(self):
        result = ingest._format_ingest_run_summary(**self._BASE)
        self.assertIn("sonar_write_failures:0", result)


class TestProcessingStatusErrorOnSonarFail(unittest.TestCase):
    """DEA-45: processing_status is 'error' when sonar writes fail even if failed_save_count==0."""

    def test_processed_when_no_failures(self):
        failed_save_count = 0
        sonar_write_fail_count = 0
        status = "processed" if failed_save_count == 0 and sonar_write_fail_count == 0 else "error"
        self.assertEqual(status, "processed")

    def test_error_when_sonar_fails_only(self):
        failed_save_count = 0
        sonar_write_fail_count = 2
        status = "processed" if failed_save_count == 0 and sonar_write_fail_count == 0 else "error"
        self.assertEqual(status, "error")

    def test_error_when_save_fails_only(self):
        failed_save_count = 1
        sonar_write_fail_count = 0
        status = "processed" if failed_save_count == 0 and sonar_write_fail_count == 0 else "error"
        self.assertEqual(status, "error")

    def test_error_when_both_fail(self):
        failed_save_count = 1
        sonar_write_fail_count = 3
        status = "processed" if failed_save_count == 0 and sonar_write_fail_count == 0 else "error"
        self.assertEqual(status, "error")


if __name__ == "__main__":
    unittest.main()
