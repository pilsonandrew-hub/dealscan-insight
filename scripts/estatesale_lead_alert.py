#!/usr/bin/env python3
"""Send EstateSale review leads to the DealerScope alerts channel."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import sys
import urllib.request
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import estatesale_keyword_watch as watcher


DEFAULT_ALERTS_CHAT_ID = "-1003672399222"
DEFAULT_SOURCE_URLS = [
    "https://www.estatesale.com/cities/view/384/Estate-Sales-Orange-CA.html",
]


def _html(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def _split_urls(raw_urls: str | None) -> list[str]:
    if not raw_urls:
        return DEFAULT_SOURCE_URLS
    normalized = raw_urls.replace(",", "\n")
    return [line.strip() for line in normalized.splitlines() if line.strip()]


def _link(url: str, label: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{_html(label)}</a>'


def format_telegram_message(report: dict[str, Any]) -> str:
    payload = report.get("review_payload") if isinstance(report.get("review_payload"), dict) else {}
    lots = payload.get("sample_vehicle_lots") if isinstance(payload.get("sample_vehicle_lots"), list) else []
    catalogs = payload.get("downstream_catalog_links") if isinstance(payload.get("downstream_catalog_links"), list) else []
    candidates = payload.get("sample_candidates") if isinstance(payload.get("sample_candidates"), list) else []

    lines = [
        "🛰 <b>EstateSale Lead Radar</b>",
        _html(payload.get("summary") or "EstateSale lead review"),
        "",
        f"Status: <b>{_html(report.get('status'))}</b>",
        f"Role: <b>{_html(payload.get('estatesale_role'))}</b>",
        f"Handoff: <b>{_html(payload.get('recommended_handoff'))}</b>",
        f"Vehicle lots: <b>{int(payload.get('vehicle_lot_count') or 0)}</b>",
        f"Candidates: <b>{int(payload.get('candidate_count') or 0)}</b>",
        "",
        f"Truth: {_html(payload.get('truth_note') or 'Review lead only; not scored.')}",
    ]

    if catalogs:
        lines.extend(["", "<b>Catalog links</b>"])
        for link in catalogs[:5]:
            lines.append(f"• {_html(link.get('source'))}: {_link(str(link.get('url') or ''), str(link.get('title') or 'catalog'))}")

    if lots:
        lines.extend(["", "<b>Sample lots</b>"])
        for lot in lots[:5]:
            title = lot.get("title") or "vehicle lot"
            vin = lot.get("vin") or "VIN n/a"
            miles = lot.get("miles")
            miles_text = f", {int(miles):,} mi" if isinstance(miles, int) else ""
            lines.append(f"• {_link(str(lot.get('lot_url') or ''), str(title))} — {_html(vin)}{miles_text}")
    elif candidates:
        lines.extend(["", "<b>Sample candidates</b>"])
        for candidate in candidates[:5]:
            title = candidate.get("title") or "lead"
            lines.append(f"• {_link(str(candidate.get('url') or ''), str(title))}")

    return "\n".join(lines)


def send_telegram(bot_token: str, chat_id: str, message: str) -> dict[str, Any]:
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
    ).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
        body = json.loads(response.read())
    if not body.get("ok"):
        raise RuntimeError(f"telegram_send_failed: {body.get('description') or body}")
    return body


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="append", help="EstateSale URL to inspect. Repeat for multiple URLs.")
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--browser-wait-ms", type=int, default=1500)
    parser.add_argument("--delay-seconds", type=float, default=watcher.DEFAULT_DELAY_SECONDS)
    parser.add_argument("--send-empty", action="store_true", help="Send an alert even when no lead signal is found.")
    parser.add_argument("--dry-run", action="store_true", help="Print message without sending Telegram.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    urls = args.url or _split_urls(os.getenv("ESTATESALE_URLS"))
    report_args = watcher.build_parser().parse_args(
        [
            "--browser",
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--browser-wait-ms",
            str(args.browser_wait_ms),
            "--delay-seconds",
            str(args.delay_seconds),
            *[part for url in urls for part in ("--url", url)],
        ]
    )
    report = watcher.build_report(report_args)
    message = format_telegram_message(report)
    has_signal = bool(report.get("vehicle_lot_count") or report.get("candidate_count") or report.get("downstream_catalog_links"))

    if args.dry_run or not has_signal and not args.send_empty:
        print(message)
        if not has_signal:
            print("\nNo EstateSale lead signal found; Telegram send skipped.", file=sys.stderr)
        return 0

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID") or DEFAULT_ALERTS_CHAT_ID
    if not bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or BOT_TOKEN is required to send EstateSale alerts")
    result = send_telegram(bot_token, chat_id, message)
    print(json.dumps({"sent": True, "message_id": result.get("result", {}).get("message_id")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
