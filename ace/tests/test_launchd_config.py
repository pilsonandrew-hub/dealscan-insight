import plistlib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CYCLE_PLIST = REPO_ROOT / "launchd" / "ai.superace.cycle.plist"


class LaunchdConfigTests(unittest.TestCase):
    def test_cycle_launchd_pins_safe_telegram_transport(self) -> None:
        with CYCLE_PLIST.open("rb") as handle:
            plist = plistlib.load(handle)

        env = plist.get("EnvironmentVariables", {})

        self.assertEqual(env.get("ACE_OPERATOR_CHANNEL"), "telegram")
        self.assertEqual(env.get("ACE_OPERATOR_TARGET"), "7529788084")
        self.assertEqual(env.get("ACE_TELEGRAM_TRANSPORT"), "openclaw_session")
        self.assertNotIn("ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN", env)
        self.assertNotIn("ACE_TELEGRAM_BOT_TOKEN", env)


if __name__ == "__main__":
    unittest.main()
