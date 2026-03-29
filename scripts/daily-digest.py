#!/usr/bin/env python3
"""DealerScope Daily Digest — queries active high-DOS vehicles and sends to Telegram."""
import json, urllib.request, ssl, datetime, sys

SUPABASE_URL = "https://lbnxzvqppccajllsqaaw.supabase.co"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxibnh6dnFwcGNjYWpsbHNxYWF3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzIwMTQ3MSwiZXhwIjoyMDg4Nzc3NDcxfQ.gLFMWuEVDbwMMHYL1CPRwNv1oGukhBTFYZGYTuXftSg"
BOT_TOKEN = "8770839167:AAEPvbNtS5Fr3LPmoEUM-9CJ14r7OXhIgzI"
CHAT_ID = "-1003672399222"

ctx = ssl._create_unverified_context()

req = urllib.request.Request(
    f"{SUPABASE_URL}/rest/v1/opportunities?select=title,state,current_bid,dos_score,listing_url,source&is_active=eq.true&dos_score=gte.70&order=dos_score.desc&limit=8",
    headers={"Authorization": f"Bearer {SERVICE_KEY}", "apikey": SERVICE_KEY}
)
with urllib.request.urlopen(req, context=ctx) as r:
    deals = json.loads(r.read())

now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
if not deals:
    text = f"📊 <b>DealerScope Daily Digest</b>\n<i>{now}</i>\n\nNo active deals scored ≥70."
else:
    lines = [f"📊 <b>DealerScope Daily Digest</b>\n<i>{now}</i>\n<b>Top Active Deals (DOS ≥70)</b>\n"]
    for i, d in enumerate(deals, 1):
        lines.append(f"{i}. <b>{d.get('title','?')[:45]}</b>")
        lines.append(f"   DOS {d.get('dos_score')} | ${d.get('current_bid',0):,.0f} | {d.get('state','?')} | {d.get('source','?')}")
        if d.get('listing_url'):
            lines.append(f"   <a href=\"{d['listing_url']}\">View Listing</a>")
    text = "\n".join(lines)

payload = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
req2 = urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
    data=payload, headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req2, context=ctx) as r:
    print(f"Sent digest: {len(deals)} deals")
