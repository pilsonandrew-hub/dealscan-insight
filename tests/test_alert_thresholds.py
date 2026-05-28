from backend.ingest.alert_thresholds import build_alert_thresholds, hot_deal_min_score


class DummyLog:
    def __init__(self):
        self.messages = []

    def warning(self, msg, *args):
        self.messages.append(msg % args)


def test_build_alert_thresholds_uses_defaults():
    thresholds = build_alert_thresholds({})

    assert thresholds.min_score == 80.0
    assert thresholds.platinum_min_roi_day == 75.0
    assert thresholds.min_bid_headroom == 0.0
    assert thresholds.min_trust_score == 0.25
    assert thresholds.min_confidence == 55.0


def test_build_alert_thresholds_reads_environment_values():
    thresholds = build_alert_thresholds(
        {
            "HOT_DEAL_MIN_SCORE": "81.5",
            "PLATINUM_MIN_ROI_DAY": "91",
            "ALERT_MIN_BID_HEADROOM": "2500",
            "ALERT_MIN_TRUST_SCORE": "0.7",
            "ALERT_MIN_CONFIDENCE": "67",
        }
    )

    assert thresholds.min_score == 81.5
    assert thresholds.platinum_min_roi_day == 91.0
    assert thresholds.min_bid_headroom == 2500.0
    assert thresholds.min_trust_score == 0.7
    assert thresholds.min_confidence == 67.0


def test_build_alert_thresholds_warns_and_defaults_invalid_values():
    log = DummyLog()

    thresholds = build_alert_thresholds({"HOT_DEAL_MIN_SCORE": "bad"}, log=log)

    assert thresholds.min_score == 80.0
    assert log.messages == ["[ALERT_GATE] Invalid HOT_DEAL_MIN_SCORE='bad'; using 80.0"]


def test_hot_deal_min_score_matches_threshold_default_and_context():
    log = DummyLog()

    assert hot_deal_min_score({"HOT_DEAL_MIN_SCORE": "bad"}, log=log) == 80.0
    assert log.messages == ["[ALERT_GATE] Invalid HOT_DEAL_MIN_SCORE='bad'; using 80.0"]
