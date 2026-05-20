#!/usr/bin/env python3
"""DealerScope Daily Digest — queries active high-DOS vehicles and sends to Telegram."""
import datetime
import json
import os
import ssl
import sys
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("CHAT_ID")
MIN_SCORE = int(os.environ.get("DAILY_DIGEST_MIN_SCORE", "70"))
LIMIT = int(os.environ.get("DAILY_DIGEST_LIMIT", "8"))

ctx = ssl.create_default_context()


def fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def require_env() -> None:
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SERVICE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SERVICE_KEY")
    if not BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN or BOT_TOKEN")
    if not CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID or CHAT_ID")
    if missing:
        fail(f"Missing required configuration: {', '.join(missing)}")


def supabase_get(path: str):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={"Authorization": f"Bearer {SERVICE_KEY}", "apikey": SERVICE_KEY},
    )
    with urllib.request.urlopen(req, context=ctx) as response:
        return json.loads(response.read())


def send_telegram(text: str):
    payload = json.dumps(
        {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=ctx) as response:
        return json.loads(response.read())


def main() -> None:
    require_env()

    deals = supabase_get(
        "opportunities?select=title,state,current_bid,dos_score,listing_url,source_site"
        f"&is_active=eq.true&dos_score=gte.{MIN_SCORE}&order=dos_score.desc&limit={LIMIT}"
    )

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not deals:
        text = f"📊 <b>DealerScope Daily Digest</b>\n<i>{now}</i>\n\nNo active deals scored ≥{MIN_SCORE}."
    else:
        lines = [
            f"📊 <b>DealerScope Daily Digest</b>\n<i>{now}</i>\n<b>Top Active Deals (DOS ≥{MIN_SCORE})</b>\n"
        ]
        for i, deal in enumerate(deals, 1):
            lines.append(f"{i}. <b>{deal.get('title', '?')[:45]}</b>")
            lines.append(
                f"   DOS {deal.get('dos_score')} | ${deal.get('current_bid', 0):,.0f} | {deal.get('state', '?')} | {deal.get('source_site', '?')}"
            )
            if deal.get("listing_url"):
                lines.append(f"   <a href=\"{deal['listing_url']}\">View Listing</a>")
        text = "\n".join(lines)

    result = send_telegram(text)
    if not result.get("ok"):
        fail(f"Telegram send failed: {result}")

    print(f"Sent digest: {len(deals)} deals")


if __name__ == "__main__":
    main()
