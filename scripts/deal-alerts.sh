#!/usr/bin/env bash
# DealerScope alert runner — grade-first, env-driven, no backend hop.

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
import urllib.request

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
HOT_DEAL_MIN_SCORE = float(os.environ.get("HOT_DEAL_MIN_SCORE", "80"))
PLATINUM_MIN_ROI_DAY = float(os.environ.get("PLATINUM_MIN_ROI_DAY", "75"))
ALERT_LIMIT = int(os.environ.get("ALERT_LIMIT", "10"))


def supabase_get(path):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={"Authorization": f"Bearer {SERVICE_KEY}", "apikey": SERVICE_KEY}
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


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


def send_telegram(text):
    payload = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


alerted_ids = set()
try:
    logs = supabase_get("alert_log?select=opportunity_id&channel=eq.telegram")
    alerted_ids = {r["opportunity_id"] for r in logs if r.get("opportunity_id")}
except Exception:
    pass

deals = supabase_get(
    "opportunities?select=id,title,year,make,model,state,current_bid,dos_score,listing_url,image_url,"
    "investment_grade,roi_per_day,bid_headroom,max_bid,processed_at"
    f"&or=(dos_score.gte.{HOT_DEAL_MIN_SCORE},investment_grade.eq.Platinum)"
    f"&order=dos_score.desc&limit={max(ALERT_LIMIT * 3, 20)}"
)

seen_ids = set()
new_alerts = []
for deal in deals:
    deal_id = deal.get("id")
    if not deal_id or deal_id in alerted_ids or deal_id in seen_ids:
        continue
    seen_ids.add(deal_id)
    grade = deal.get("investment_grade")
    roi_day = float(deal.get("roi_per_day") or 0)
    headroom = float(deal.get("bid_headroom") or 0)
    score = float(deal.get("dos_score") or 0)
    is_platinum = grade == "Platinum" and roi_day >= PLATINUM_MIN_ROI_DAY and headroom > 0
    is_hot = score >= HOT_DEAL_MIN_SCORE
    if not (is_platinum or is_hot):
        continue
    deal["_alert_type"] = "platinum" if is_platinum else "hot"
    new_alerts.append(deal)
    if len(new_alerts) >= ALERT_LIMIT:
        break

if not new_alerts:
    print("No new alerts to send")
    sys.exit(0)

print(f"Found {len(new_alerts)} new alerts to send")

for deal in new_alerts:
    title = deal.get("title", "Unknown Vehicle")
    bid = deal.get("current_bid", 0)
    dos = deal.get("dos_score", 0)
    state = deal.get("state", "??")
    url = deal.get("listing_url", "")
    grade = deal.get("investment_grade", "Watch")
    alert_type = deal.get("_alert_type", "hot")

    if alert_type == "platinum":
        roi_day = float(deal.get("roi_per_day") or 0)
        headroom = float(deal.get("bid_headroom") or 0)
        max_bid = float(deal.get("max_bid") or 0)
        msg = (
            f"💎 <b>PLATINUM ALERT</b>\n\n"
            f"<b>{title}</b>\n"
            f"🏅 Grade: <b>{grade}</b>\n"
            f"📊 Score: {dos}/100\n"
            f"💰 Current bid: <b>${bid:,.0f}</b>\n"
            f"🎯 Max bid: <b>${max_bid:,.0f}</b>\n"
            f"📈 ROI/day: <b>${roi_day:,.0f}</b>\n"
            f"🛟 Headroom: <b>${headroom:,.0f}</b>\n"
            f"📍 {state}\n"
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
            f"\n<a href=\"{url}\">View on auction site →</a>"
        )

    try:
        send_telegram(msg)
        print(f"  ✅ Alerted ({alert_type}): {title} | Score:{dos}")
        supabase_post("alert_log", {
            "opportunity_id": deal["id"],
            "channel": "telegram",
            "vehicle_title": title[:200],
            "dos_score": dos,
            "message_id": f"tg-{deal['id'][:8]}",
            "delivery_state": "sent",
            "sent_at": datetime.datetime.utcnow().isoformat()
        })
    except Exception as e:
        print(f"  ❌ Failed to alert {title}: {e}")

PYEOF
