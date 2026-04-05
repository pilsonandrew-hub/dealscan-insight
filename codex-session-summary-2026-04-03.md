# DealerScope Pipeline Audit Summary

Date: 2026-04-03

## Findings

1. AllSurplus actor output in `apify/actors/ds-allsurplus/src/main.js` aligns with `normalize_apify_vehicle()` for the audited fields.
   - `listing_url` is emitted and read correctly
   - `current_bid` is emitted and read correctly
   - `state` is emitted and read correctly
   - `source_site` is emitted and read correctly
   - `auction_end_date` is emitted and read correctly via the normalizer
   - `mileage` is emitted as `null` in this listing feed; the normalizer accepts it if present

2. GSA actor output in `apify/actors/ds-gsaauctions/src/main.js` also aligns with `normalize_apify_vehicle()` for the audited fields.
   - `listing_url`, `current_bid`, `state`, and `source_site` are emitted as expected
   - `auction_end_date` is emitted as ISO and is accepted by the normalizer

3. `_normalize_auction_end_time()` in `webapp/routers/ingest.py` handles the formats observed in the actors and the relative formats already supported by the parser.
   - Verified ISO `...Z` strings from both actors
   - Verified compact relative formats like `1d 2h`
   - Verified countdown formats like `45:00`

4. Proxy-only confidence is now preserved end-to-end.
   - `score_deal()` returns `mmr_confidence_proxy`
   - `alert_gating.py` still blocks low-confidence proxy-only rows at the default `min_confidence=55.0`
   - That is consistent with the conservative alerting policy documented in the repo

5. Bronze hard-drop was overbroad.
   - The ingest loop in `webapp/routers/ingest.py` no longer drops every Bronze record before save
   - Bronze rows are now governed by the existing `ceiling_pass` gate instead of being rejected twice

## Verification

- `python3 -m py_compile backend/ingest/score.py webapp/routers/ingest.py tests/test_ingest_scoring.py backend/ingest/alert_gating.py`
- Direct `python3` assertions confirmed:
  - ISO end-time normalization
  - compact relative end-time normalization
  - alert gating blocks low-confidence proxy-only rows
  - `score_deal()` returns `mmr_confidence_proxy`

## Notes

- `pytest` is not installed in this environment, so I could not run the full test suite.
- Unrelated workspace files such as `package.json`, `backend/.cache/`, and `webapp/routers/__pycache__/ingest.cpython-314.pyc` were left untouched.
