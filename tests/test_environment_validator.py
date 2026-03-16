import os
import unittest
from unittest.mock import patch

from config.environment_validator import EnvironmentValidator


class EnvironmentValidatorWebhookSecretTests(unittest.TestCase):
    def test_production_rejects_placeholder_active_webhook_secret(self):
        env = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 32,
            "DATABASE_URL": "postgresql://user:password@db.example/dealerscope",
            "APIFY_WEBHOOK_SECRET": "your_webhook_secret_here",
        }
        with patch.dict(os.environ, env, clear=True):
            result = EnvironmentValidator().validate_all()

        self.assertIn(
            "APIFY_WEBHOOK_SECRET is set to a placeholder-like value",
            result["errors"],
        )

    def test_production_rejects_duplicate_previous_webhook_secret(self):
        secret = "a" * 32
        env = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 32,
            "DATABASE_URL": "postgresql://user:password@db.example/dealerscope",
            "APIFY_WEBHOOK_SECRET": secret,
            "APIFY_WEBHOOK_SECRET_PREVIOUS": secret,
        }
        with patch.dict(os.environ, env, clear=True):
            result = EnvironmentValidator().validate_all()

        self.assertIn(
            "APIFY_WEBHOOK_SECRET_PREVIOUS must differ from APIFY_WEBHOOK_SECRET",
            result["errors"],
        )

    def test_rotation_overlap_warns_until_previous_secret_is_removed(self):
        env = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 32,
            "DATABASE_URL": "postgresql://user:password@db.example/dealerscope",
            "APIFY_WEBHOOK_SECRET": "n" * 32,
            "APIFY_WEBHOOK_SECRET_PREVIOUS": "o" * 32,
        }
        with patch.dict(os.environ, env, clear=True):
            result = EnvironmentValidator().validate_all()

        self.assertIn(
            "APIFY_WEBHOOK_SECRET_PREVIOUS is configured; remove it after rotation completes",
            result["warnings"],
        )
        self.assertTrue(result["valid"])


if __name__ == "__main__":
    unittest.main()
