#!/usr/bin/env python3
"""Read-only EstateSale.com keyword watcher.

This is intentionally a lead-discovery scraper, not a DealerScope ingest actor.
It reports vehicle/tool/trailer-like sale pages for human review and fails
explicitly when EstateSale serves a bot/challenge page.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request


DEFAULT_URLS = ["https://www.estatesale.com/cities/view/384/Estate-Sales-Orange-CA.html"]
DEFAULT_DELAY_SECONDS = 10.0
USER_AGENT = "Mozilla/5.0 (compatible; DealerScopeLeadWatcher/1.0; +https://github.com/pilsonandrew-hub/dealscan-insight)"

DEFAULT_KEYWORDS = [
    "Honda",
    "Toyota",
    "Ford",
    "Lexus",
    "Mercedes",
    "Chevrolet",
    "Dodge",
    "Ram",
    "GMC",
    "Jeep",
    "Nissan",
    "Subaru",
    "VIN",
    "motorcycle",
    "pickup",
    "truck",
    "SUV",
    "trailer",
    "vehicle",
    "classic car",
    "estate vehicle",
    "equipment",
    "tools",
]

VEHICLE_MAKES = {
    "Acura",
    "Audi",
    "BMW",
    "Buick",
    "Cadillac",
    "Chevrolet",
    "Chrysler",
    "Dodge",
    "Ford",
    "GMC",
    "Honda",
    "Hyundai",
    "Jeep",
    "Kawasaki",
    "Kia",
    "Lexus",
    "Mazda",
    "Mercedes",
    "Nissan",
    "Ram",
    "Subaru",
    "Toyota",
}

HIGH_INTENT_KEYWORDS = {
    "Honda",
    "Toyota",
    "Ford",
    "Lexus",
    "Mercedes",
    "Chevrolet",
    "Dodge",
    "Ram",
    "GMC",
    "Jeep",
    "Nissan",
    "Subaru",
    "VIN",
    "motorcycle",
    "pickup",
    "truck",
    "SUV",
    "trailer",
    "vehicle",
    "classic car",
    "estate vehicle",
}


DOWNSTREAM_CATALOG_LABELS = {
    "view online catalog",
    "online bidding platform",
}

IGNORED_LINK_TITLES = {
    "about estatesale.com",
    "add your company",
    "advertise your sale",
    "contact us",
    "email notifications",
    "free email notifications",
    "hire a company",
    "home",
    "member login",
    "sign up now!",
}


@dataclass(frozen=True)
class LinkRecord:
    href: str
    text: str
    start_chunk_index: int
    end_chunk_index: int


class LinkContextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_chunks: list[str] = []
        self.links: list[LinkRecord] = []
        self._active_href: str | None = None
        self._active_text: list[str] = []
        self._active_start_index = 0
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag != "a":
            return
        attrs_dict = {key.lower(): value for key, value in attrs}
        href = attrs_dict.get("href")
        if not href:
            return
        self._active_href = href
        self._active_text = []
        self._active_start_index = len(self.text_chunks)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag != "a" or self._active_href is None:
            return
        link_text = _normalize_space(" ".join(self._active_text))
        self.links.append(
            LinkRecord(
                href=self._active_href,
                text=link_text,
                start_chunk_index=self._active_start_index,
                end_chunk_index=max(self._active_start_index, len(self.text_chunks) - 1),
            )
        )
        self._active_href = None
        self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = _normalize_space(data)
        if not text:
            return
        self.text_chunks.append(text)
        if self._active_href is not None:
            self._active_text.append(text)


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _is_blocked_challenge(markup: str) -> bool:
    lowered = markup.lower()
    has_challenge_marker = any(
        marker in lowered
        for marker in (
            "_incapsula_resource",
            "incap_ses_",
            "visid_incap_",
            "imperva",
        )
    )
    if not has_challenge_marker:
        return False
    has_real_sale_content = any(
        marker in lowered
        for marker in (
            "listing id#",
            "sale location",
            "view online catalog",
            "sale dates and times",
        )
    )
    return not has_real_sale_content


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])", re.IGNORECASE)


def _matched_keywords(text: str, keywords: Iterable[str]) -> list[str]:
    return [keyword for keyword in keywords if _keyword_pattern(keyword).search(text)]


def _absolute_url(href: str, source_url: str) -> str:
    return urllib_parse.urljoin(source_url, href)


def _is_navigable_url(url: str) -> bool:
    parsed = urllib_parse.urlparse(url)
    if parsed.scheme in {"javascript", "mailto", "tel"}:
        return False
    if not parsed.scheme and not parsed.netloc and (url or "").strip().startswith("#"):
        return False
    return bool(url and url.strip())


def _context_for_link(parser: LinkContextParser, index: int) -> str:
    link = parser.links[index]
    next_start = parser.links[index + 1].start_chunk_index if index + 1 < len(parser.links) else len(parser.text_chunks)
    chunks = parser.text_chunks[link.start_chunk_index:next_start]
    return _normalize_space(" ".join(chunks))


def _priority_for(matches: list[str]) -> str:
    return "review" if any(match in HIGH_INTENT_KEYWORDS for match in matches) else "lead"


def _extract_regex(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return _normalize_space(match.group(1))


def _extract_vin(text: str) -> str | None:
    match = re.search(r"\b[A-HJ-NPR-Z0-9]{17}\b", text, flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def _extract_int(pattern: str, text: str) -> int | None:
    value = _extract_regex(pattern, text)
    if not value or value.lower() == "unknown":
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def _extract_year(text: str) -> int | None:
    year = _extract_int(r"\bYear:\s*(\d{4})\b", text)
    if year:
        return year
    title_year = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    return int(title_year.group(1)) if title_year else None


def _extract_make(title: str, context: str) -> str | None:
    make = _extract_regex(r"\bMake:\s*([A-Za-z]+)\b", context)
    if make:
        return make
    for candidate in sorted(VEHICLE_MAKES, key=len, reverse=True):
        if _keyword_pattern(candidate).search(title):
            return candidate
    return None


def _extract_model(context: str) -> str | None:
    return _extract_regex(r"\bModel:\s*(.+?)(?:\s+Engine:|\s+Miles:|\s+Keys:|\s+Runs:|\s+Title Status:|$)", context)


def _first_present(*values: str | int | None) -> str | int | None:
    return next((value for value in values if value is not None), None)


def _extract_vehicle_lot(link: LinkRecord, url: str, context: str) -> dict[str, object] | None:
    vin = _extract_vin(context)
    year = _extract_year(context)
    make = _extract_make(link.text, context)
    model = _extract_model(context)
    if not (vin and year and make):
        return None

    lot: dict[str, object] = {
        "lot_url": url,
        "title": link.text or url,
        "vin": vin,
        "year": year,
        "make": make,
        "model": model,
        "miles": _first_present(
            _extract_int(r"\bMiles:\s*([0-9,]+|unknown)\b", context),
            _extract_int(r"\bOdometer reads:\s*([0-9,]+|unknown)\b", context),
        ),
        "keys": _first_present(
            _extract_regex(r"\bKeys:\s*(.+?)(?:\s+Runs:|\s+Title Status:|$)", context),
            _extract_regex(r"\bKeys\?:\s*(.+?)(?:\s+Started\?:|\s+Notice:|$)", context),
        ),
        "runs": _first_present(
            _extract_regex(r"\bRuns:\s*(.+?)(?:\s+Title Status:|$)", context),
            _extract_regex(r"\bStarted\?:\s*(.+?)(?:\s+Notice:|\s+Title Status:|$)", context),
        ),
        "title_status": _extract_regex(r"\bTitle Status:\s*(.+?)(?:\s+Odometer Status:|\s+notes:|$)", context),
        "odometer_status": _extract_regex(r"\bOdometer Status:\s*(.+?)(?:\s+notes:|$)", context),
        "snippet": context[:360],
    }
    return {key: value for key, value in lot.items() if value is not None}


def _downstream_source(url: str) -> str:
    hostname = urllib_parse.urlparse(url).hostname or ""
    hostname = hostname.lower()
    if "govdeals.com" in hostname:
        return "govdeals"
    if "hibid.com" in hostname:
        return "hibid"
    if hostname and "estatesale.com" not in hostname:
        return "external_auction"
    return "estatesale"


def _is_downstream_catalog_link(link: LinkRecord, url: str) -> bool:
    text = link.text.lower()
    if any(label in text for label in DOWNSTREAM_CATALOG_LABELS):
        return _downstream_source(url) != "estatesale"
    return _downstream_source(url) == "govdeals"


def _extract_downstream_catalog_links(parser: LinkContextParser, source_url: str) -> list[dict[str, str]]:
    catalog_links: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for link in parser.links:
        url = _absolute_url(link.href, source_url)
        if url in seen_urls or not _is_navigable_url(url) or not _is_downstream_catalog_link(link, url):
            continue
        seen_urls.add(url)
        catalog_links.append(
            {
                "url": url,
                "title": link.text or url,
                "source": _downstream_source(url),
            }
        )
    return catalog_links


def _estatesale_role(catalog_links: list[dict[str, str]], vehicle_lots: list[dict[str, object]], candidates: list[dict[str, object]]) -> str:
    if vehicle_lots and catalog_links:
        return "structured_vehicle_lot_signpost"
    if catalog_links:
        return "downstream_catalog_signpost"
    if vehicle_lots:
        return "structured_vehicle_lot_page"
    if candidates:
        return "lead_discovery"
    return "no_vehicle_signal"


def _recommended_handoff(catalog_links: list[dict[str, str]], vehicle_lots: list[dict[str, object]], candidates: list[dict[str, object]]) -> str:
    sources = {link["source"] for link in catalog_links}
    if len(sources) > 1:
        return "mixed_downstream_review"
    if "govdeals" in sources:
        return "dealer_scope_govdeals_pipeline"
    if "hibid" in sources:
        return "downstream_hibid_or_catalog_review"
    if "external_auction" in sources:
        return "external_catalog_review"
    if vehicle_lots:
        return "vehicle_lot_review"
    if candidates:
        return "lead_review_alert"
    return "ignore"


def _build_review_payload(
    *,
    source_url: str,
    status: str,
    estatesale_role: str,
    recommended_handoff: str,
    downstream_catalog_links: list[dict[str, str]],
    vehicle_lots: list[dict[str, object]],
    candidates: list[dict[str, object]],
) -> dict[str, object]:
    summary = (
        "EstateSale lead: "
        f"role={estatesale_role}; handoff={recommended_handoff}; "
        f"vehicle_lots={len(vehicle_lots)}; candidates={len(candidates)}; "
        f"downstream_sources={','.join(sorted({link['source'] for link in downstream_catalog_links})) or 'none'}"
    )
    return {
        "destination": "dealerscope_alerts",
        "lead_source": "estatesale",
        "source_url": source_url,
        "status": status,
        "estatesale_role": estatesale_role,
        "recommended_handoff": recommended_handoff,
        "vehicle_lot_count": len(vehicle_lots),
        "candidate_count": len(candidates),
        "downstream_catalog_links": downstream_catalog_links,
        "sample_vehicle_lots": vehicle_lots[:5],
        "sample_candidates": candidates[:5],
        "summary": summary,
        "truth_note": "Review lead only; not scored and not saved as a DealerScope opportunity yet.",
    }


def _is_ignored_link(link: LinkRecord) -> bool:
    title = _normalize_space(link.text).lower()
    return title in IGNORED_LINK_TITLES


def analyze_html(
    markup: str,
    *,
    source_url: str,
    keywords: Iterable[str] = DEFAULT_KEYWORDS,
) -> dict[str, object]:
    generated_at = datetime.now(timezone.utc).isoformat()
    if _is_blocked_challenge(markup):
        return {
            "status": "blocked",
            "blocked_reason": "imperva_incapsula_challenge",
            "source_url": source_url,
            "generated_at": generated_at,
            "candidate_count": 0,
            "candidates": [],
            "vehicle_lot_count": 0,
            "vehicle_lots": [],
            "downstream_catalog_links": [],
            "estatesale_role": "blocked",
            "recommended_handoff": "retry_with_browser_or_proxy",
            "review_payload": _build_review_payload(
                source_url=source_url,
                status="blocked",
                estatesale_role="blocked",
                recommended_handoff="retry_with_browser_or_proxy",
                downstream_catalog_links=[],
                vehicle_lots=[],
                candidates=[],
            ),
        }

    parser = LinkContextParser()
    parser.feed(markup)
    candidates: list[dict[str, object]] = []
    vehicle_lots: list[dict[str, object]] = []
    downstream_catalog_links = _extract_downstream_catalog_links(parser, source_url)
    seen_urls: set[str] = set()
    seen_lot_urls: set[str] = set()
    keyword_list = list(keywords)

    for index, link in enumerate(parser.links):
        if _is_ignored_link(link):
            continue
        url = _absolute_url(link.href, source_url)
        if not _is_navigable_url(url):
            continue
        context = _context_for_link(parser, index)
        vehicle_lot = _extract_vehicle_lot(link, url, context)
        if vehicle_lot and url not in seen_lot_urls:
            seen_lot_urls.add(url)
            vehicle_lots.append(vehicle_lot)
        if url in seen_urls:
            continue
        matches = _matched_keywords(context, keyword_list)
        if not matches:
            continue
        seen_urls.add(url)
        candidates.append(
            {
                "url": url,
                "title": link.text or url,
                "matched_keywords": matches,
                "priority": _priority_for(matches),
                "snippet": context[:360],
            }
        )

    if not candidates and not vehicle_lots and not downstream_catalog_links:
        page_context = _normalize_space(" ".join(parser.text_chunks))
        matches = _matched_keywords(page_context, keyword_list)
        if matches:
            candidates.append(
                {
                    "url": source_url,
                    "title": "EstateSale page lead",
                    "matched_keywords": matches,
                    "priority": _priority_for(matches),
                    "snippet": page_context[:360],
                }
            )

    return {
        "status": "ok",
        "source_url": source_url,
        "generated_at": generated_at,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "vehicle_lot_count": len(vehicle_lots),
        "vehicle_lots": vehicle_lots,
        "downstream_catalog_links": downstream_catalog_links,
        "estatesale_role": (role := _estatesale_role(downstream_catalog_links, vehicle_lots, candidates)),
        "recommended_handoff": (handoff := _recommended_handoff(downstream_catalog_links, vehicle_lots, candidates)),
        "review_payload": _build_review_payload(
            source_url=source_url,
            status="ok",
            estatesale_role=role,
            recommended_handoff=handoff,
            downstream_catalog_links=downstream_catalog_links,
            vehicle_lots=vehicle_lots,
            candidates=candidates,
        ),
    }


def fetch_html(url: str, *, timeout_seconds: int = 30, verify_tls: bool = True) -> str:
    request = urllib_request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    context = None if verify_tls else ssl._create_unverified_context()  # noqa: S323
    with urllib_request.urlopen(request, timeout=timeout_seconds, context=context) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def fetch_html_browser(url: str, *, timeout_seconds: int = 45, wait_ms: int = 1500) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(f"browser_fetch_unavailable: {exc}") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1365, "height": 900},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            if wait_ms > 0:
                page.wait_for_timeout(wait_ms)
            return page.content()
        finally:
            browser.close()


def build_report(args: argparse.Namespace) -> dict[str, object]:
    keywords = args.keyword or DEFAULT_KEYWORDS
    if args.html_file:
        markup = args.html_file.read_text(encoding="utf-8")
        source_url = args.source_url or str(args.html_file)
        return analyze_html(markup, source_url=source_url, keywords=keywords)

    urls = args.url or DEFAULT_URLS
    reports = []
    for index, url in enumerate(urls):
        if index:
            time.sleep(max(0.0, args.delay_seconds))
        try:
            if args.browser:
                markup = fetch_html_browser(
                    url,
                    timeout_seconds=args.timeout_seconds,
                    wait_ms=args.browser_wait_ms,
                )
            else:
                markup = fetch_html(
                    url,
                    timeout_seconds=args.timeout_seconds,
                    verify_tls=not args.allow_insecure,
                )
            reports.append(analyze_html(markup, source_url=url, keywords=keywords))
        except urllib_error.HTTPError as exc:
            reports.append(_error_report(url, f"http_{exc.code}"))
        except (TimeoutError, urllib_error.URLError, RuntimeError) as exc:
            reports.append(_error_report(url, f"fetch_failed: {exc}"))

    all_candidates = [candidate for report in reports for candidate in report.get("candidates", [])]
    all_vehicle_lots = [lot for report in reports for lot in report.get("vehicle_lots", [])]
    all_downstream_catalog_links = [
        link for report in reports for link in report.get("downstream_catalog_links", [])
    ]
    status = "ok"
    if reports and all(report.get("status") == "blocked" for report in reports):
        status = "blocked"
    elif any(report.get("status") == "error" for report in reports):
        status = "partial_error"
    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "estatesale.com",
        "report_count": len(reports),
        "candidate_count": len(all_candidates),
        "candidates": all_candidates,
        "vehicle_lot_count": len(all_vehicle_lots),
        "vehicle_lots": all_vehicle_lots,
        "downstream_catalog_links": all_downstream_catalog_links,
        "estatesale_role": (role := _estatesale_role(all_downstream_catalog_links, all_vehicle_lots, all_candidates)),
        "recommended_handoff": (handoff := _recommended_handoff(all_downstream_catalog_links, all_vehicle_lots, all_candidates)),
        "review_payload": _build_review_payload(
            source_url=", ".join(urls),
            status=status,
            estatesale_role=role,
            recommended_handoff=handoff,
            downstream_catalog_links=all_downstream_catalog_links,
            vehicle_lots=all_vehicle_lots,
            candidates=all_candidates,
        ),
        "reports": reports,
    }


def _error_report(source_url: str, reason: str) -> dict[str, object]:
    return {
        "status": "error",
        "error": reason,
        "source_url": source_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_count": 0,
        "candidates": [],
        "vehicle_lot_count": 0,
        "vehicle_lots": [],
        "downstream_catalog_links": [],
        "estatesale_role": "fetch_error",
        "recommended_handoff": "retry_or_review_manually",
        "review_payload": _build_review_payload(
            source_url=source_url,
            status="error",
            estatesale_role="fetch_error",
            recommended_handoff="retry_or_review_manually",
            downstream_catalog_links=[],
            vehicle_lots=[],
            candidates=[],
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="append", help="EstateSale page URL to inspect. Repeat for multiple pages.")
    parser.add_argument("--html-file", type=Path, help="Local HTML fixture to inspect.")
    parser.add_argument("--source-url", help="Source URL to use when resolving links from --html-file.")
    parser.add_argument("--keyword", action="append", help="Override keyword list. Repeat for multiple keywords.")
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--browser", action="store_true", help="Fetch pages with Playwright Chromium before parsing.")
    parser.add_argument("--browser-wait-ms", type=int, default=1500)
    parser.add_argument(
        "--allow-insecure",
        action="store_true",
        help="Disable TLS certificate verification for diagnostics only.",
    )
    return parser


def run_cli(argv: list[str] | None = None) -> tuple[int, str]:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_report(args)
    return 0, json.dumps(report, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    exit_code, output = run_cli(argv)
    print(output, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
