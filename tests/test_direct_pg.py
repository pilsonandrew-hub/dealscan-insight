from psycopg2 import extras as psycopg2_extras

from backend.ingest.direct_pg import prepare_direct_pg_value


def test_prepare_direct_pg_value_wraps_dict_as_json_adapter():
    value = {"a": 1}
    prepared = prepare_direct_pg_value(value)

    assert isinstance(prepared, psycopg2_extras.Json)
    assert prepared.adapted == value


def test_prepare_direct_pg_value_leaves_scalar_values_unchanged():
    assert prepare_direct_pg_value("abc") == "abc"
    assert prepare_direct_pg_value(123) == 123
    assert prepare_direct_pg_value(None) is None
