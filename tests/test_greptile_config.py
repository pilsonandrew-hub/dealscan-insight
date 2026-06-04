import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_greptile_reviews_are_manual_only_to_control_flex_overage():
    config_path = REPO_ROOT / ".greptile" / "config.json"

    assert config_path.exists(), "Greptile config must exist to override dashboard auto-review defaults"

    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert config.get("skipReview") == "AUTOMATIC"
    assert config.get("triggerOnUpdates") is False
    assert config.get("statusCheck") is False
