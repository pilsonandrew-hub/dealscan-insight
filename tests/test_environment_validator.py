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
            "SUPABASE_SERVICE_ROLE_KEY": "s" * 40,
            "APIFY_TOKEN": "a" * 32,
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

    def test_production_requires_supabase_service_role_key_for_ingest(self):
        env = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 32,
            "DATABASE_URL": "postgresql://user:password@db.example/dealerscope",
            "APIFY_TOKEN": "a" * 32,
            "APIFY_WEBHOOK_SECRET": "n" * 32,
        }
        with patch.dict(os.environ, env, clear=True):
            result = EnvironmentValidator().validate_all()

        self.assertIn(
            "SUPABASE_SERVICE_ROLE_KEY is required for privileged ingest operations",
            result["errors"],
        )

    def test_production_requires_apify_token_for_ingest(self):
        env = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 32,
            "DATABASE_URL": "postgresql://user:password@db.example/dealerscope",
            "SUPABASE_SERVICE_ROLE_KEY": "s" * 40,
            "APIFY_WEBHOOK_SECRET": "n" * 32,
        }
        with patch.dict(os.environ, env, clear=True):
            result = EnvironmentValidator().validate_all()

        self.assertIn(
            "APIFY_TOKEN or APIFY_API_TOKEN is required for Apify ingest",
            result["errors"],
        )

    def test_live_pager_requires_telegram_credentials_when_not_dry_run(self):
        env = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 32,
            "DATABASE_URL": "postgresql://user:password@db.example/dealerscope",
            "SUPABASE_SERVICE_ROLE_KEY": "s" * 40,
            "APIFY_TOKEN": "a" * 32,
            "APIFY_WEBHOOK_SECRET": "n" * 32,
            "INGEST_HEALTH_NOTIFY_ENABLED": "true",
            "INGEST_HEALTH_NOTIFY_DRY_RUN": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            result = EnvironmentValidator().validate_all()

        self.assertIn(
            "TELEGRAM_BOT_TOKEN is required when ingest pager notifications are enabled",
            result["errors"],
        )
        self.assertIn(
            "TELEGRAM_CHAT_ID is required when ingest pager notifications are enabled",
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
