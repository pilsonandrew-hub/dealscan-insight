import json
from pathlib import Path
import unittest


class ApifyDeploymentManifestTests(unittest.TestCase):
    def test_deployment_manifest_does_not_store_webhook_secret(self):
        manifest_path = (
            Path(__file__).resolve().parent.parent / "apify" / "deployment.json"
        )
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertNotIn("webhookSecret", payload)


if __name__ == "__main__":
    unittest.main()
