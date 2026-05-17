from backend.ingest.vin_dedup import check_vin_duplicate, normalize_vin


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def select(self, value):
        self.calls.append(("select", value))
        return self

    def eq(self, field, value):
        self.calls.append(("eq", field, value))
        return self

    def gte(self, field, value):
        self.calls.append(("gte", field, value))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def execute(self):
        self.calls.append(("execute",))
        return _Result(self.data)


class _Client:
    def __init__(self, data):
        self.query = _Query(data)

    def table(self, name):
        self.query.calls.append(("table", name))
        return self.query


def test_normalize_vin_strips_and_uppercases():
    assert normalize_vin("  abc123  ") == "ABC123"
    assert normalize_vin("   ") is None
    assert normalize_vin(None) is None


def test_check_vin_duplicate_returns_update_when_new_score_higher():
    client = _Client([{"id": "opp-1", "dos_score": 70}])

    assert check_vin_duplicate("VIN123", 75, supabase_client=client, now_iso="2026-01-01T00:00:00+00:00") == ("opp-1", True)
    assert ("table", "opportunities") in client.query.calls
    assert ("eq", "vin", "VIN123") in client.query.calls
    assert ("gte", "auction_end_date", "2026-01-01T00:00:00+00:00") in client.query.calls


def test_check_vin_duplicate_does_not_update_when_score_not_higher():
    client = _Client([{"id": "opp-1", "dos_score": 75}])

    assert check_vin_duplicate("VIN123", 75, supabase_client=client, now_iso="2026-01-01T00:00:00+00:00") == ("opp-1", False)


def test_check_vin_duplicate_no_client_or_no_rows():
    assert check_vin_duplicate("VIN123", 75, supabase_client=None) == (None, False)
    assert check_vin_duplicate("VIN123", 75, supabase_client=_Client([]), now_iso="2026-01-01T00:00:00+00:00") == (None, False)
