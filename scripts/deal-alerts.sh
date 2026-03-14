#!/usr/bin/env bash
# DealerScope Hot Deal Alerts — runs via cron, sends Telegram when DOS >= 80
# Bypasses Railway entirely — queries Supabase directly

SUPABASE_URL="${SUPABASE_URL:-}"
SUPABASE_KEY="${SUPABASE_SERVICE_ROLE_KEY:-}"
TELEGRAM_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT="${TELEGRAM_CHAT_ID:-}"

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

hot_deals = supabase_get(
    "opportunities?select=id,title,year,make,model,state,current_bid,dos_score,listing_url,image_url"
    "&dos_score=gte.80&order=dos_score.desc&limit=10"
)

new_alerts = [d for d in hot_deals if d["id"] not in alerted_ids]

if not new_alerts:
    print("No new hot deals to alert")
    sys.exit(0)

print(f"Found {len(new_alerts)} new hot deals to alert")

for deal in new_alerts:
    title = deal.get("title", "Unknown Vehicle")
    bid = deal.get("current_bid", 0)
    dos = deal.get("dos_score", 0)
    state = deal.get("state", "??")
    url = deal.get("listing_url", "")

    msg = (
        f"🔥 <b>HOT DEAL — DOS {dos}</b>\n\n"
        f"<b>{title}</b>\n"
        f"💰 Current bid: <b>${bid:,.0f}</b>\n"
        f"📍 {state}\n"
        f"📊 Score: {dos}/100\n"
        f"\n<a href=\"{url}\">View on auction site →</a>"
    )

    try:
        send_telegram(msg)
        print(f"  ✅ Alerted: {title} | DOS:{dos}")
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
