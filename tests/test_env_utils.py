import logging

from backend.ingest.env_utils import env_float, env_int


class CapturingLogger:
    def __init__(self):
        self.messages = []

    def warning(self, msg, *args):
        self.messages.append(msg % args)


def test_env_float_returns_default_for_missing_or_blank():
    assert env_float({}, "HOT_DEAL_MIN_SCORE", 70.0) == 70.0
    assert env_float({"HOT_DEAL_MIN_SCORE": ""}, "HOT_DEAL_MIN_SCORE", 70.0) == 70.0


def test_env_float_parses_valid_value():
    assert env_float({"HOT_DEAL_MIN_SCORE": "82.5"}, "HOT_DEAL_MIN_SCORE", 70.0) == 82.5


def test_env_float_warns_and_defaults_for_invalid_value():
    log = CapturingLogger()
    assert env_float({"HOT_DEAL_MIN_SCORE": "nope"}, "HOT_DEAL_MIN_SCORE", 70.0, log=log, context="ALERT_GATE") == 70.0
    assert log.messages == ["[ALERT_GATE] Invalid HOT_DEAL_MIN_SCORE='nope'; using 70.0"]


def test_env_int_returns_default_for_missing_or_blank():
    assert env_int({}, "APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS", 3600) == 3600
    assert env_int({"APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS": ""}, "APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS", 3600) == 3600


def test_env_int_parses_valid_value():
    assert env_int({"APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS": "120"}, "APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS", 3600) == 120


def test_env_int_warns_and_defaults_for_invalid_value():
    log = CapturingLogger()
    assert env_int({"APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS": "slow"}, "APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS", 3600, log=log, context="INGEST_AUTH") == 3600
    assert log.messages == ["[INGEST_AUTH] Invalid APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS='slow'; using 3600"]
