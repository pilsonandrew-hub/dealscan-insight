"""DealerScope deal expiry sweeper.

Keeps lifecycle rules testable instead of hiding them inside workflow YAML.
"""

from __future__ import annotations

import datetime as _datetime
import json
import os
import ssl
import urllib.request
from collections.abc import Callable, Iterable
from typing import Any

from supabase import create_client


def _fetch_ids(supabase: Any, filters: Iterable[Callable[[Any], Any]]) -> list[str]:
    ids: list[str] = []
    offset = 0
    page_size = 500
    while True:
        query = supabase.table("opportunities").select("id").order("id")
        for filter_fn in filters:
            query = filter_fn(query)
        response = query.range(offset, offset + page_size - 1).execute()
        rows = response.data or []
        if not rows:
            break
        ids.extend(row["id"] for row in rows if row.get("id"))
        if len(rows) < page_size:
            break
        offset += page_size
    return ids


def _chunked(values: list[str], size: int = 200):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _update_batches(supabase: Any, ids: list[str], payload: dict[str, Any]) -> int:
    count = 0
    for batch in _chunked(ids):
        supabase.table("opportunities").update(payload).in_("id", batch).execute()
        count += len(batch)
    return count


def build_message(summary: dict[str, Any]) -> str:
    return (
        "🧹 <b>DealerScope Deal Expiry Sweeper</b>\n\n"
        f"Expired deals: <b>{summary['expired']}</b>\n"
        f"Archived passed deals: <b>{summary['archived_passed']}</b>\n"
        "Archived stale saved/inactive deals: "
        f"<b>{summary['archived_stale_saved_inactive']}</b>\n"
        f"Run time: {summary['run_time']}"
    )


def run_sweep(
    supabase: Any,
    *,
    now: _datetime.datetime | None = None,
    notify: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    now = now or _datetime.datetime.now(_datetime.timezone.utc)
    expired_cutoff = (now - _datetime.timedelta(hours=24)).isoformat()
    archive_cutoff = (now - _datetime.timedelta(days=7)).isoformat()

    expired_ids = _fetch_ids(
        supabase,
        [
            lambda q: q.lt("auction_end_date", expired_cutoff),
            lambda q: q.neq("pipeline_step", "expired"),
            lambda q: q.eq("is_active", True),
        ],
    )
    archived_passed_ids = _fetch_ids(
        supabase,
        [
            lambda q: q.eq("pipeline_step", "passed"),
            lambda q: q.lt("updated_at", archive_cutoff),
        ],
    )
    stale_saved_inactive_ids = _fetch_ids(
        supabase,
        [
            lambda q: q.eq("pipeline_step", "saved"),
            lambda q: q.eq("is_active", False),
            lambda q: q.lt("updated_at", archive_cutoff),
        ],
    )

    summary = {
        "expired": _update_batches(
            supabase,
            expired_ids,
            {"is_active": False, "pipeline_step": "expired"},
        ),
        "archived_passed": _update_batches(
            supabase,
            archived_passed_ids,
            {"pipeline_step": "archived"},
        ),
        "archived_stale_saved_inactive": _update_batches(
            supabase,
            stale_saved_inactive_ids,
            {"pipeline_step": "archived"},
        ),
        "run_time": now.strftime("%Y-%m-%d %H:%M UTC"),
    }

    if notify:
        summary["notification_ok"] = notify(build_message(summary))
    return summary


def _send_telegram(text: str) -> bool:
    bot_token = os.environ["BOT_TOKEN"]
    chat_id = os.environ["CHAT_ID"]
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
    ).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=ssl.create_default_context()) as resp:
        json.loads(resp.read())
    print("Telegram notification sent")
    return True


def _safe_send_telegram(text: str) -> bool:
    try:
        return _send_telegram(text)
    except Exception as exc:
        print(f"Telegram notification failed: {exc}")
        return False


def main() -> int:
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    summary = run_sweep(supabase, notify=_safe_send_telegram)
    print(build_message(summary).replace("<b>", "").replace("</b>", ""))
    if not summary.get("notification_ok", True):
        print(
            "Sweep completed, but Telegram delivery failed; "
            "investigate TELEGRAM_BOT_TOKEN / chat permissions."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
