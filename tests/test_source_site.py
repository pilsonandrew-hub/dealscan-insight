from backend.ingest.source_site import canonical_source_site, infer_source_site, source_site_from_url


def test_canonical_source_site_preserves_existing_aliases():
    assert canonical_source_site("GovDeals") == "govdeals"
    assert canonical_source_site("govdeals_sold") == "govdeals-sold"
    assert canonical_source_site("hibid-v2") == "hibid"
    assert canonical_source_site("publicsurplus_tx") == "publicsurplus"


def test_canonical_source_site_ignores_non_source_placeholders():
    assert canonical_source_site("") == ""
    assert canonical_source_site("apify") == ""
    assert canonical_source_site("unknown") == ""
    assert canonical_source_site(None) == ""


def test_source_site_from_url_uses_existing_host_hints():
    assert source_site_from_url("https://www.govdeals.com/asset/123") == "govdeals"
    assert source_site_from_url("https://gsaauctions.gov/lot/123") == "gsaauctions"
    assert source_site_from_url("https://example.com/lot/123") == ""


def test_infer_source_site_prefers_explicit_fields_before_hint_and_url():
    item = {
        "source_site": "publicsurplus_tx",
        "source": "govdeals",
        "listing_url": "https://www.proxibid.com/lot/1",
    }

    assert infer_source_site(item, source_hint="hibid-v2") == "publicsurplus"


def test_infer_source_site_falls_back_to_hint_then_url():
    assert infer_source_site({"source_site": "apify"}, source_hint="hibid-v2") == "hibid"
    assert infer_source_site({"url": "https://www.jjkane.com/auctions/1"}) == "jjkane"
    assert infer_source_site({"url": "https://example.com/auctions/1"}) is None
