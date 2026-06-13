#!/usr/bin/env bash
# DealerScope alert runner — grade-first, env-driven, no backend hop.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

SUPABASE_URL="${SUPABASE_URL:-}"
SUPABASE_KEY="${SUPABASE_SERVICE_ROLE_KEY:-}"
TELEGRAM_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT="${TELEGRAM_CHAT_ID:-}"
HOT_DEAL_MIN_SCORE="${HOT_DEAL_MIN_SCORE:-80}"
PLATINUM_MIN_ROI_DAY="${PLATINUM_MIN_ROI_DAY:-75}"
ALERT_LIMIT="${ALERT_LIMIT:-10}"

if [[ -z "$SUPABASE_URL" || -z "$SUPABASE_KEY" || -z "$TELEGRAM_TOKEN" || -z "$TELEGRAM_CHAT" ]]; then
  echo "Error: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, TELEGRAM_BOT_TOKEN, and TELEGRAM_CHAT_ID must be set." >&2
  exit 1
fi

python3 << 'PYEOF'
import datetime
import json
import os
import sys
import urllib.parse
import urllib.request

from backend.ingest.alert_gating import AlertThresholds, evaluate_alert_gate
from backend.ingest.listing_identity import compute_listing_id

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
HOT_DEAL_MIN_SCORE = float(os.environ.get("HOT_DEAL_MIN_SCORE", "80"))
PLATINUM_MIN_ROI_DAY = float(os.environ.get("PLATINUM_MIN_ROI_DAY", "75"))
ALERT_LIMIT = int(os.environ.get("ALERT_LIMIT", "10"))
CANDIDATE_LIMIT = max(ALERT_LIMIT * 2, 10)
ALERT_MIN_TRUST_SCORE = float(os.environ.get("ALERT_MIN_TRUST_SCORE", "0.25"))
ALERT_MIN_CONFIDENCE = float(os.environ.get("ALERT_MIN_CONFIDENCE", "55"))
ALERT_MIN_BID_HEADROOM = float(os.environ.get("ALERT_MIN_BID_HEADROOM", "0"))
ALERT_DEBUG = os.environ.get("ALERT_DEBUG", "true").lower() == "true"

THRESHOLDS = AlertThresholds(
    min_score=HOT_DEAL_MIN_SCORE,
    platinum_min_roi_day=PLATINUM_MIN_ROI_DAY,
    min_bid_headroom=ALERT_MIN_BID_HEADROOM,
    min_trust_score=ALERT_MIN_TRUST_SCORE,
    min_confidence=ALERT_MIN_CONFIDENCE,
)


def supabase_get(path):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={"Authorization": f"Bearer {SERVICE_KEY}", "apikey": SERVICE_KEY}
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def fetch_raw_data_by_id(opportunity_ids):
    ids = [str(opportunity_id) for opportunity_id in opportunity_ids if opportunity_id]
    if not ids:
        return {}
    encoded_ids = ",".join(urllib.parse.quote(opportunity_id, safe="") for opportunity_id in ids)
    rows = supabase_get(f"opportunities?select=id,raw_data&id=in.({encoded_ids})")
    return {row.get("id"): row.get("raw_data") for row in rows if row.get("id")}


def supabase_post(table, row):
    payload = json.dumps(row).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{table}",
        data=payload,
        headers={
            "Authorization": f"Bearer {SERVICE_KEY}",
            "apikey": SERVICE_KEY,
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        },
        method="POST"
    )
    with urllib.request.urlopen(req) as r:
        return r.status


def normalize_alert_type(value):
    normalized = str(value or "").strip().lower()
    if normalized in {"hot", "hot_deal"}:
        return "hot"
    if normalized == "platinum":
        return "platinum"
    return normalized


def alert_type_satisfies(current_alert_type, prior_alert_type):
    current = normalize_alert_type(current_alert_type)
    prior = normalize_alert_type(prior_alert_type) or "hot"
    if not current:
        return bool(prior)
    if current == "platinum":
        return prior == "platinum"
    if current == "hot":
        return prior in {"hot", "platinum"}
    return prior == current


def send_telegram(text):
    payload = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


alerted_types_by_id = {}
try:
    logs = supabase_get("alert_log?select=opportunity_id,alert_type,delivery_state&channel=eq.telegram")
    for row in logs:
        opportunity_id = row.get("opportunity_id")
        if not opportunity_id or str(row.get("delivery_state") or "sent").lower() == "failed":
            continue
        alerted_types_by_id.setdefault(opportunity_id, set()).add(normalize_alert_type(row.get("alert_type")))
except Exception:
    pass

deals = supabase_get(
    "opportunities?select=id,listing_id,run_id,source_site,title,year,make,model,state,current_bid,dos_score,listing_url,image_url,"
    "investment_grade,roi_per_day,estimated_days_to_sale,bid_headroom,max_bid,processed_at,pricing_maturity,pricing_source,"
    "current_bid_trust_score,mmr_confidence_proxy,acquisition_price_basis,acquisition_basis_source,"
    "projected_total_cost,expected_close_bid,expected_close_source,gross_margin,mmr_lookup_basis,"
    "retail_comp_count,retail_comp_confidence,vin,mileage,condition_grade,vehicle_tier"
    "&is_active=eq.true"
    f"&or=(dos_score.gte.{HOT_DEAL_MIN_SCORE},investment_grade.eq.Gold,investment_grade.eq.Platinum)"
    f"&order=dos_score.desc&limit={CANDIDATE_LIMIT}"
)

raw_data_needed_ids = []
for deal in deals:
    preliminary_gate = evaluate_alert_gate(deal, thresholds=THRESHOLDS)
    if "condition_unverified" in preliminary_gate.get("blocking_reasons", []):
        raw_data_needed_ids.append(deal.get("id"))
raw_data_by_id = fetch_raw_data_by_id(raw_data_needed_ids)
for deal in deals:
    raw_data = raw_data_by_id.get(deal.get("id"))
    if raw_data is not None:
        deal["raw_data"] = raw_data

seen_ids = set()
new_alerts = []
blocked_candidates = []
for deal in deals:
    deal_id = deal.get("id")
    if not deal_id or deal_id in seen_ids:
        continue
    seen_ids.add(deal_id)
    gate = evaluate_alert_gate(deal, thresholds=THRESHOLDS)
    deal["_alert_gate"] = gate
    if not gate["eligible"]:
        blocked_candidates.append(deal)
        continue
    alert_type = normalize_alert_type(gate.get("alert_type")) or "hot"
    if any(alert_type_satisfies(alert_type, prior) for prior in alerted_types_by_id.get(deal_id, set())):
        continue
    deal["_alert_type"] = gate["alert_type"]
    new_alerts.append(deal)
    if len(new_alerts) >= ALERT_LIMIT:
        break

if not new_alerts:
    if ALERT_DEBUG and blocked_candidates:
        print("Blocked alert candidates:")
        for deal in blocked_candidates[:10]:
            gate = deal["_alert_gate"]
            print(
                "  - "
                f"{deal.get('title', 'Unknown Vehicle')[:80]} | "
                f"{gate['summary']} | reasons={','.join(gate['blocking_reasons'])}"
            )
    print("No new alerts to send")
    sys.exit(0)

print(f"Found {len(new_alerts)} new alerts to send")
if ALERT_DEBUG and blocked_candidates:
    print("Blocked alert candidates:")
    for deal in blocked_candidates[:10]:
        gate = deal["_alert_gate"]
        print(
            "  - "
            f"{deal.get('title', 'Unknown Vehicle')[:80]} | "
            f"{gate['summary']} | reasons={','.join(gate['blocking_reasons'])}"
        )

for deal in new_alerts:
    title = deal.get("title", "Unknown Vehicle")
    bid = deal.get("current_bid", 0)
    dos = deal.get("dos_score", 0)
    state = deal.get("state", "??")
    url = deal.get("listing_url", "")
    grade = deal.get("investment_grade", "Watch")
    alert_type = deal.get("_alert_type", "hot")
    gate = deal.get("_alert_gate", {})
    signals = gate.get("signals", {})
    trust_score = signals.get("current_bid_trust_score")
    confidence = signals.get("confidence")
    pricing_maturity = signals.get("pricing_maturity", deal.get("pricing_maturity", "unknown"))
    pricing_source = signals.get("pricing_source", deal.get("pricing_source", "unknown"))
    expected_close_source = signals.get("expected_close_source", deal.get("expected_close_source", "unknown"))
    acquisition_basis_source = signals.get("acquisition_basis_source", deal.get("acquisition_basis_source", "unknown"))
    mmr_lookup_basis = signals.get("mmr_lookup_basis", deal.get("mmr_lookup_basis", "unknown"))
    retail_comp_count = signals.get("retail_comp_count", deal.get("retail_comp_count"))
    retail_comp_confidence = signals.get("retail_comp_confidence", deal.get("retail_comp_confidence"))
    truth_note = ""
    if pricing_maturity == "proxy":
        truth_note = (
            "⚠️ Proxy-priced: expected close and basis are synthetic."
            f" Lookup basis: {mmr_lookup_basis}"
        )
    elif retail_comp_count not in (None, ""):
        truth_note = (
            f"🧾 Retail evidence: count={int(float(retail_comp_count))}"
            f", conf={retail_comp_confidence if retail_comp_confidence is not None else 'n/a'}"
        )

    if alert_type == "platinum":
        roi_day = float(signals.get("roi_per_day") or deal.get("roi_per_day") or 0)
        headroom = float(signals.get("bid_headroom") or deal.get("bid_headroom") or 0)
        max_bid = float(signals.get("max_bid") or deal.get("max_bid") or 0)
        msg = (
            f"💎 <b>PLATINUM ALERT</b>\n\n"
            f"<b>{title}</b>\n"
            f"🏅 Grade: <b>{grade}</b>\n"
            f"📊 Score: {dos}/100\n"
            f"💰 Current bid: <b>${bid:,.0f}</b>\n"
            f"🎯 Max bid: <b>${max_bid:,.0f}</b>\n"
            f"📈 ROI/day: <b>${roi_day:,.0f}</b>\n"
            f"🛟 Headroom: <b>${headroom:,.0f}</b>\n"
            f"🧭 Pricing: <b>{pricing_maturity}</b> via {pricing_source}\n"
            f"🔐 Trust/Conf: <b>{trust_score if trust_score is not None else 'n/a'}</b> / <b>{confidence if confidence is not None else 'n/a'}</b>\n"
            f"🧮 Expected close: <b>{expected_close_source}</b>\n"
            f"📐 Basis: <b>{acquisition_basis_source}</b>\n"
            f"📍 {state}\n"
            f"{truth_note}\n"
            f"\n<a href=\"{url}\">View on auction site →</a>"
        )
    else:
        msg = (
            f"🔥 <b>HOT DEAL ALERT</b>\n\n"
            f"<b>{title}</b>\n"
            f"🏅 Grade: <b>{grade}</b>\n"
            f"💰 Current bid: <b>${bid:,.0f}</b>\n"
            f"📍 {state}\n"
            f"📊 Score: {dos}/100\n"
            f"🧭 Pricing: <b>{pricing_maturity}</b> via {pricing_source}\n"
            f"🔐 Trust/Conf: <b>{trust_score if trust_score is not None else 'n/a'}</b> / <b>{confidence if confidence is not None else 'n/a'}</b>\n"
            f"🧮 Expected close: <b>{expected_close_source}</b>\n"
            f"📐 Basis: <b>{acquisition_basis_source}</b>\n"
            f"{truth_note}\n"
            f"\n<a href=\"{url}\">View on auction site →</a>"
        )

    try:
        telegram_result = send_telegram(msg)
        message_id = str((telegram_result.get("result") or {}).get("message_id") or f"tg-{deal['id'][:8]}")
        print(f"  ✅ Alerted ({alert_type}): {title} | Score:{dos}")
        supabase_post("alert_log", {
            "opportunity_id": deal["id"],
            "channel": "telegram",
            "alert_type": "platinum" if alert_type == "platinum" else "hot",
            "vehicle_title": title[:200],
            "dos_score": dos,
            "message_id": message_id,
            "delivery_state": "sent",
            "sent_at": datetime.datetime.utcnow().isoformat()
        })
        listing_id = deal.get("listing_id") or compute_listing_id(deal.get("source_site") or "", deal.get("listing_url") or "")
        supabase_post("ingest_delivery_log", {
            "run_id": f"active-alerts-{alert_type}-{datetime.datetime.utcnow().strftime('%Y%m%d%H')}",
            "listing_id": listing_id or deal["id"],
            "listing_url": deal.get("listing_url"),
            "opportunity_id": deal["id"],
            "channel": "telegram_alert",
            "status": "sent",
            "external_id": message_id,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat()
        })
    except Exception as e:
        print(f"  ❌ Failed to alert {title}: {e}")

PYEOF
