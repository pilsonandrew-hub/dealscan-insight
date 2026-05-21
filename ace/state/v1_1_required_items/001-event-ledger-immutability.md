# V1.1 Required Item — Event Ledger Immutability

Status: REQUIRED_NOT_STARTED

Requirement: harden ACE so semantic event rows cannot be modified outside a governed correction path without durable disclosure. Any repair/rewrite operation must produce append-only correction evidence before/with the repair and must preserve original values or a recoverable snapshot.

Reason: 2026-05-21 ledger contamination showed that direct SQLite mutation plus forward rehash can restore hash-chain consistency while destroying original truth.
