import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "page_recent_ingest_health.sh"


class PageRecentIngestHealthTests(unittest.TestCase):
    def _write_fake_python(self, directory: Path) -> None:
        real_python = subprocess.check_output(["bash", "-lc", "command -v python3"], text=True).strip()
        (directory / "python3").write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                if [[ "${{1:-}}" == *"check_recent_ingest_runs.py" ]]; then
                  echo "simulated ingest health failure" >&2
                  exit 1
                fi
                exec "{real_python}" "$@"
                """
            ),
            encoding="utf-8",
        )
        os.chmod(directory / "python3", 0o755)

    def _write_sitecustomize(self, directory: Path) -> None:
        (directory / "sitecustomize.py").write_text(
            textwrap.dedent(
                """\
                import io
                import os
                from urllib import request as _request

                payload = os.environ.get("MOCK_TELEGRAM_JSON")
                if payload:
                    class _MockResponse:
                        def __init__(self, body):
                            self._body = body.encode("utf-8")

                        def read(self):
                            return self._body

                        def __enter__(self):
                            return self

                        def __exit__(self, exc_type, exc, tb):
                            return False

                    def _mock_urlopen(req, timeout=0):
                        url = getattr(req, "full_url", req)
                        if "api.telegram.org" in str(url):
                            return _MockResponse(payload)
                        raise AssertionError(f"unexpected urlopen target: {url}")

                    _request.urlopen = _mock_urlopen
                """
            ),
            encoding="utf-8",
        )

    def _run_wrapper(self, env_file_contents: str, *, mock_telegram_json: str | None = None) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            self._write_fake_python(fake_bin)
            self._write_sitecustomize(tmp_path)
            env_file = tmp_path / ".env.live"
            env_file.write_text(env_file_contents, encoding="utf-8")

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            env["PYTHONPATH"] = f"{tmp_path}:{env.get('PYTHONPATH', '')}"
            if mock_telegram_json is not None:
                env["MOCK_TELEGRAM_JSON"] = mock_telegram_json

            return subprocess.run(
                ["bash", str(SCRIPT_PATH), "--env-file", str(env_file)],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_env_file_drives_dry_run_pager_gating(self):
        completed = self._run_wrapper(
            "\n".join(
                [
                    "INGEST_HEALTH_NOTIFY_ENABLED=true",
                    "INGEST_HEALTH_NOTIFY_DRY_RUN=true",
                    "TELEGRAM_BOT_TOKEN=test-token",
                    "TELEGRAM_CHAT_ID=test-chat",
                ]
            )
        )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("[DRY RUN] Telegram alert suppressed.", completed.stderr)
        self.assertIn("DealerScope ingest health check failed", completed.stderr)

    def test_live_mode_fails_when_telegram_does_not_acknowledge_page(self):
        completed = self._run_wrapper(
            "\n".join(
                [
                    "INGEST_HEALTH_NOTIFY_ENABLED=true",
                    "INGEST_HEALTH_NOTIFY_DRY_RUN=false",
                    "TELEGRAM_BOT_TOKEN=test-token",
                    "TELEGRAM_CHAT_ID=test-chat",
                ]
            ),
            mock_telegram_json='{"ok": false, "description": "chat not found"}',
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("telegram send failed: chat not found", completed.stderr)


if __name__ == "__main__":
    unittest.main()
