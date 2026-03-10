import os
import time
import logging
import requests
from lxml import html
from dataclasses import dataclass
from typing import Iterator, Optional


@dataclass
class Row:
    url: str
    title: str
    year: Optional[int]
    make: str
    model: str
    state: str
    bid: float
    end: str
    desc: str


class GovDealsLive:
    BASE = "https://www.govdeals.com/index.cfm"
    HEADERS = {"User-Agent": "DealerScope/1.0 (+internal; research)"}

    def __init__(self, category_id: str = "16", delay_sec: float = 1.5):
        self.category_id = category_id
        self.delay_sec = delay_sec
        proxy = os.getenv("HTTP_PROXY")
        self.proxies = {"http": proxy, "https": proxy} if proxy else None

    def _fetch_page(self, page: int, retries: int = 3) -> Optional[html.HtmlElement]:
        params = {
            "fa": "Main.CategorySearch",
            "kWord": "",
            "catID": self.category_id,
            "page": str(page),
        }
        for attempt in range(retries):
            try:
                r = requests.get(
                    self.BASE,
                    params=params,
                    headers=self.HEADERS,
                    proxies=self.proxies,
                    timeout=20,
                )
                r.raise_for_status()
                return html.fromstring(r.content)
            except requests.RequestException as e:
                logging.warning(f"GovDeals page {page} attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        logging.error(f"GovDeals page {page} failed after {retries} attempts.")
        return None

    def _text(self, node, xp, default=""):
        v = (node.xpath(xp) or [default])[0]
        return v.strip() if isinstance(v, str) else v

    def iter_rows(self, pages: int = 3) -> Iterator[dict]:
        for p in range(1, pages + 1):
            doc = self._fetch_page(p)
            if not doc:
                continue
            for n in doc.xpath('//div[contains(@id, "container_item")]'):
                try:
                    href = self._text(n, './/a[@class="item_title"]/@href', "")
                    title = self._text(n, './/a[@class="item_title"]/text()', "")
                    year_str = title.split()[0] if title else ""
                    year = int(year_str) if year_str.isdigit() and len(year_str) == 4 else None
                    location_text = self._text(n, './/div[b="Location:"]/text()', "")
                    state = location_text.split(",")[-1].strip() if "," in location_text else ""
                    bid_txt = self._text(
                        n, './/div[contains(text(), "Current bid:")]/b/text()', "$0"
                    )
                    bid = float(bid_txt.replace("$", "").replace(",", ""))
                    end = self._text(
                        n, './/div[contains(text(), "Auction ends:")]/b/text()', ""
                    )
                    yield {
                        "url": href,
                        "title": title,
                        "year": year,
                        "make": "",
                        "model": "",
                        "state": state,
                        "bid": bid,
                        "end": end,
                        "desc": title,
                    }
                except (ValueError, IndexError) as e:
                    logging.warning(f"Could not parse listing node: {e}")
                    continue
            time.sleep(self.delay_sec)
