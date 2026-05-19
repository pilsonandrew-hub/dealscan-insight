import plistlib
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CYCLE_PLIST = REPO_ROOT / "launchd" / "ai.superace.cycle.plist"
CYCLE_RUNNER = REPO_ROOT / "launchd" / "run-ace-cycle.sh"


class LaunchdConfigTests(unittest.TestCase):
    def test_cycle_launchd_routes_notifications_to_jace_owned_channel(self) -> None:
        with CYCLE_PLIST.open("rb") as handle:
            plist = plistlib.load(handle)

        env = plist.get("EnvironmentVariables", {})

        self.assertEqual(env.get("ACE_OPERATOR_CHANNEL"), "telegram")
        self.assertEqual(env.get("ACE_OPERATOR_TARGET"), "7529788084")
        self.assertEqual(env.get("ACE_TELEGRAM_TRANSPORT"), "telegram_bot_api")
        self.assertNotIn("ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN", env)
        self.assertNotIn("ACE_TELEGRAM_BOT_TOKEN", env)

    def test_cycle_runner_supports_env_configured_sweep_thresholds(self) -> None:
        script = CYCLE_RUNNER.read_text(encoding="utf-8")

        self.assertIn('TRIAGE_AFTER_HOURS="${ACE_TRIAGE_AFTER_HOURS:-24}"', script)
        self.assertIn('APPROVED_AFTER_HOURS="${ACE_APPROVED_AFTER_HOURS:-72}"', script)
        self.assertIn('BLOCKED_AFTER_HOURS="${ACE_BLOCKED_AFTER_HOURS:-24}"', script)
        self.assertIn('CLAIMED_DONE_AFTER_HOURS="${ACE_CLAIMED_DONE_AFTER_HOURS:-24}"', script)
        self.assertIn('ACTIVE_AFTER_HOURS="${ACE_ACTIVE_AFTER_HOURS:-72}"', script)
        self.assertIn('--triage-after-hours "$TRIAGE_AFTER_HOURS"', script)
        self.assertIn('--approved-after-hours "$APPROVED_AFTER_HOURS"', script)
        self.assertIn('--blocked-after-hours "$BLOCKED_AFTER_HOURS"', script)
        self.assertIn('--claimed-done-after-hours "$CLAIMED_DONE_AFTER_HOURS"', script)
        self.assertIn('--active-after-hours "$ACTIVE_AFTER_HOURS"', script)

        subprocess.run(["zsh", "-n", str(CYCLE_RUNNER)], check=True)


if __name__ == "__main__":
    unittest.main()
