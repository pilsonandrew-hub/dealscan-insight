"""Telegram alert formatting helpers for DealerScope ingest.

Pure helpers only: no network sends, logging, suppression, or routing decisions.
"""

from __future__ import annotations

import html
from typing import Any
from urllib.parse import quote


def redact_telegram_bot_token(text: Any) -> str:
    """Redact Telegram bot tokens embedded in exception strings or URLs."""
    return __import__("re").sub(
        r"bot[0-9]{6,}:[A-Za-z0-9_-]+",
        "bot[REDACTED_TELEGRAM_TOKEN]",
        str(text),
    )


def telegram_html_escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def telegram_link(url: str, label: str) -> str:
    safe_url = html.escape(str(url or ""), quote=True)
    safe_label = telegram_html_escape(label)
    return f'<a href="{safe_url}">{safe_label}</a>'


def clean_bid_direct_url(raw_listing_url: str) -> str:
    """Strip GovPlanet query params that can trigger geo-redirects."""
    if "govplanet.com" in (raw_listing_url or ""):
        return raw_listing_url.split("?")[0]
    return raw_listing_url or ""


def build_deal_url(opportunity_id: Any) -> str:
    return f"https://dealscan-insight.vercel.app/deal/{opportunity_id or ''}"


def build_telegram_reply_markup(callback_id: Any) -> dict[str, list[list[dict[str, str]]]]:
    callback_id = callback_id or "unknown"
    return {
        "inline_keyboard": [[
            {"text": "🔥 BUY", "callback_data": f"buy_{callback_id}"},
            {"text": "👀 WATCH", "callback_data": f"watch_{callback_id}"},
            {"text": "❌ PASS", "callback_data": f"pass_{callback_id}"},
        ]]
    }


def build_telegram_alert_message(deal: dict[str, Any], listing_url: str, *, alert_gate: dict[str, Any] | None = None) -> str:
    """Build the HTML Telegram alert body preserving legacy message semantics."""
    score_breakdown = deal.get("score_breakdown", {}) if isinstance(deal.get("score_breakdown"), dict) else {}
    investment_grade = score_breakdown.get("investment_grade") or "Watch"
    roi_per_day = float(score_breakdown.get("roi_per_day") or 0)
    headroom = float(score_breakdown.get("bid_headroom") or 0)
    alert_gate = alert_gate if isinstance(alert_gate, dict) else deal.get("alert_gate")
    alert_gate = alert_gate if isinstance(alert_gate, dict) else {}
    is_platinum = alert_gate.get("alert_type") == "platinum"
    gate_signals = alert_gate.get("signals", {}) if isinstance(alert_gate.get("signals"), dict) else {}

    pricing_maturity = gate_signals.get("pricing_maturity") or score_breakdown.get("pricing_maturity") or "unknown"
    pricing_source = gate_signals.get("pricing_source") or score_breakdown.get("pricing_source") or "unknown"
    trust_score = gate_signals.get("current_bid_trust_score")
    confidence = gate_signals.get("confidence")
    expected_close_source = gate_signals.get("expected_close_source") or score_breakdown.get("expected_close_source") or "unknown"
    acquisition_basis_source = gate_signals.get("acquisition_basis_source") or score_breakdown.get("acquisition_basis_source") or "unknown"
    mmr_lookup_basis = gate_signals.get("mmr_lookup_basis") or score_breakdown.get("mmr_lookup_basis") or "unknown"
    retail_comp_count = gate_signals.get("retail_comp_count")
    retail_comp_confidence = gate_signals.get("retail_comp_confidence")

    truth_note = ""
    if pricing_maturity == "proxy":
        truth_note = (
            "Proxy-priced: expected close and basis are synthetic "
            f"({telegram_html_escape(mmr_lookup_basis)})\n"
        )
    elif retail_comp_count is not None:
        truth_note = (
            "Retail evidence: "
            f"count={int(float(retail_comp_count))}, "
            f"conf={telegram_html_escape(retail_comp_confidence if retail_comp_confidence is not None else 'n/a')}\n"
        )

    deal_url = build_deal_url(deal.get("opportunity_id", ""))
    score = deal["dos_score"]

    if is_platinum:
        return (
            f"💎 <b>PLATINUM ALERT</b>\n"
            f"{telegram_html_escape(deal.get('year'))} {telegram_html_escape(deal.get('make'))} {telegram_html_escape(deal.get('model'))}\n"
            f"Grade: <b>{telegram_html_escape(investment_grade)}</b> | Score: <b>{score}</b>\n"
            f"ROI/Day: ${roi_per_day:,.0f} | Headroom: ${headroom:,.0f}\n"
            f"Bid: ${deal.get('current_bid', 0):,.0f} | Max Bid: ${score_breakdown.get('max_bid', 0):,.0f}\n"
            f"Pricing: {telegram_html_escape(pricing_maturity)} via {telegram_html_escape(pricing_source)} | Trust: {telegram_html_escape(trust_score if trust_score is not None else 'n/a')} | Conf: {telegram_html_escape(confidence if confidence is not None else 'n/a')}\n"
            f"Expected Close: {telegram_html_escape(expected_close_source)}\n"
            f"Basis: {telegram_html_escape(acquisition_basis_source)}\n"
            f"{truth_note}"
            f"State: {telegram_html_escape(deal.get('state', '?'))}\n"
            f"{telegram_link(deal_url, 'View Deal')} | {telegram_link(listing_url, 'Bid Direct →')}"
        )

    return (
        f"🔥 <b>HOT DEAL ALERT</b>\n"
        f"{telegram_html_escape(deal.get('year'))} {telegram_html_escape(deal.get('make'))} {telegram_html_escape(deal.get('model'))}\n"
        f"Grade: <b>{telegram_html_escape(investment_grade)}</b> | Score: <b>{score}</b>\n"
        f"Bid: ${deal.get('current_bid', 0):,.0f}\n"
        f"Pricing: {telegram_html_escape(pricing_maturity)} via {telegram_html_escape(pricing_source)} | Trust: {telegram_html_escape(trust_score if trust_score is not None else 'n/a')} | Conf: {telegram_html_escape(confidence if confidence is not None else 'n/a')}\n"
        f"Expected Close: {telegram_html_escape(expected_close_source)}\n"
        f"Basis: {telegram_html_escape(acquisition_basis_source)}\n"
        f"{truth_note}"
        f"State: {telegram_html_escape(deal.get('state', '?'))}\n"
        f"Gross: ${score_breakdown.get('gross_margin', 0):,.0f}\n"
        f"{telegram_link(deal_url, 'View Deal')} | {telegram_link(listing_url, 'Bid Direct →')}"
    )
