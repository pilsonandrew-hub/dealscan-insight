# ACE V1.1 Phase 1 Closeout

Date: 2026-05-21

## Scope

This closes Phase 1 baseline/adjudication work after the ACE/JACE hash-chain breach disclosure. It does not claim V1.1 completion. It records the corrected baseline that Phase 2/V1.1 hardening continues from.

## Corrected JACE classification

Corrected JACE audit baseline distinguishes actual sends from support records.

Confirmed natural JACE deliveries: **3**

- `message_id=17` — `item_d037a33658d842b49008bb0e2ec2c64e`; natural launchd-driven delivery with content-context caution.
- `message_id=18` — `item_fce588264f2a4a218b62c67cec673f17`; clean natural launchd-driven delivery.
- `message_id=19` — `item_412551ecb1344adca1698fd2afedd184`; natural launchd-driven delivery with content-context caution / follow-up to the DealerScope audit thread.

The earlier “10-row JACE audit” was incomplete because it treated `alert_log` as the only meaningful delivery surface and did not correctly cross-reference `evidence`, `action_queue`, and `governed_runs`.

## May 19 proof-context items

The May 19 items that produced phone-visible JACE deliveries are confirmed as proof/manual-context items, not natural production proof and not the same fingerprint as the disclosed direct event backdating/hash-chain rewrite.

- `item_7a564adeef6e4b029bb1fd38ab694896`
  - Created as `TRIAGE`, not legacy `ACTIVE`.
  - Proof/manual workspace residual context.
  - Produced JACE `message_id=10` and `message_id=11`.
  - Classification: proof-context delivery with send-wrapper timing anomalies, not hash-chain tampering.

- `item_b73bffc9ec82421b90a5df4b55a900bf`
  - Created as `TRIAGE`, not legacy `ACTIVE`.
  - Launchd/JACE suppression proof context.
  - Produced JACE `message_id=12` and `message_id=13`.
  - Classification: proof-context delivery with send-wrapper timing anomalies, not hash-chain tampering.

## `message_id=15`

`message_id=15` has no ACE record and no phone-visible message per Andrew's phone check. It is classified as a benign allocated-but-not-delivered Telegram/Bot API gap unless later evidence proves otherwise.

## 112 timestamp inversion adjudication

Review-required timestamp inversions: **112**

- Breach-contaminated: **4**
- Plausible, pending external/operator attestation: **96**
- Anomalous: **12**
  - Send-wrapper timing anomalies: **8**
    - Associated with May 19 proof-context JACE items.
    - Hash links are internally consistent.
    - Classification: timestamp/order anomaly in send wrapper/evidence timing, not proven hash-chain rewrite.
  - Legacy `ACTIVE`-start anomalies: **4**
    - Legacy proof items with `ACTIVE`-start/backdated-style historical construction.
    - Classification: anomalous legacy proof construction, not normal runtime production evidence.

## DealerScope audit verification result

DealerScope follow-up verification reached the intended boundary:

- Finding 3 clean: deployed frontend bundle scan found no `/api/api` double-prefix and no `VITE_API_URL` literal in the deployed bundle.
- Finding 5 clean: live `/api/rover/debug` returns `404` and is absent from OpenAPI.
- Finding 1 endpoint-verified: `/api/outcomes` exists and unauthenticated valid-shaped POST returns `401`; persistence verification deferred to normal frontend use rather than synthetic production write.
- Finding 2 endpoint-verified: `/api/analytics/scraper-status` exists and unauthenticated GET returns `401`; authenticated data-shape verification deferred until a browser/session token is intentionally provided.
- Finding 4 designed: route-contract gate design documented.
- Finding 6 known gap: `deploy-gold.yml` contains a `force_deploy` bypass that can override validation/SLO failures and suppress failure notification.

## Phase 1 closeout statement

Phase 1 is formally closed with the above corrected baseline. Phase 2 is authorized to continue from the already committed work, with remaining V1.1 controls still open:

1. External Backblaze/object-store hash attestation.
2. Behavioral constraint runtime enforcement.
3. Direct DB mutation hard lockdown.

This closeout does not erase the documented bypasses. It preserves them as governance evidence while allowing Phase 2 to continue under explicit operator authorization.
