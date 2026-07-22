from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from src.schemas.models import JudgmentItem


@dataclass
class CrawlerConfig:
    base_url: str
    headless: bool
    timeout_ms: int
    detail_timeout_ms: int = 10000


class JudicialClient:
    def __init__(self, config: CrawlerConfig) -> None:
        self.config = config

    def query_customer(self, customer_name: str) -> tuple[str, str, list[JudgmentItem]]:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.config.headless)
                context = browser.new_context()
                page = context.new_page()
                page.set_default_timeout(self.config.timeout_ms)
                page.goto(self.config.base_url)

                self._fill_search_form(page, customer_name)
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(1800)

                page_text = page.locator("body").inner_text()
                result_list_url = self._find_result_list_url(page)
                if not result_list_url and ("查無資料" in page_text or "查詢結果 0" in page_text):
                    context.close()
                    browser.close()
                    return "NO_DATA", "查無資料", []

                if result_list_url:
                    page.goto(result_list_url)
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(800)

                judgments = self._extract_result_rows(page)
                status = "FOUND" if judgments else "NO_DATA"
                note = "" if judgments else "查無資料"

                context.close()
                browser.close()
                return status, note, judgments
        except PlaywrightTimeoutError:
            return "ERROR", "查詢逾時", []
        except Exception as exc:  # noqa: BLE001
            return "ERROR", f"查詢失敗: {exc}", []

    def _fill_search_form(self, page, customer_name: str) -> None:
        page.locator("#txtKW").fill(customer_name)
        page.locator("#btnSimpleQry").click()

    def _find_result_list_url(self, page) -> str:
        links = page.locator("a")
        fallback = ""
        for idx in range(links.count()):
            anchor = links.nth(idx)
            href = anchor.get_attribute("href") or ""
            if "qryresultlst.aspx" not in href:
                continue

            full_url = urljoin(self.config.base_url, href)
            text = (anchor.inner_text() or "").strip()

            if "查詢結果" in text and "&gy=" not in href:
                return full_url
            if not fallback and "&gy=" not in href:
                fallback = full_url

        return fallback

    def _extract_result_rows(self, page) -> list[JudgmentItem]:
        rows = page.locator("table tr")
        count = rows.count()
        judgments: list[JudgmentItem] = []

        for idx in range(count):
            row = rows.nth(idx)
            cells = row.locator("td")
            if cells.count() < 4:
                continue

            serial = cells.nth(0).inner_text().strip()
            if not serial or not serial.replace(".", "").isdigit():
                continue

            raw_judgment_id = cells.nth(1).inner_text().strip()
            judgment_id = re.sub(r"\s*[（(][^）)]*K[）)]\s*$", "", raw_judgment_id).strip()
            judgment_date = cells.nth(2).inner_text().strip()
            case_type = cells.nth(3).inner_text().strip()

            detail_text, detail_url = self._extract_detail_from_row(page, row)
            judgments.append(
                JudgmentItem(
                    judgment_id=judgment_id,
                    judgment_date=judgment_date,
                    case_type=case_type,
                    full_text=detail_text,
                    source_url=detail_url,
                )
            )

        return judgments

    def _extract_detail_from_row(self, page, row) -> tuple[str, str]:
        anchor = row.locator("td").nth(1).locator("a").first
        if anchor.count() == 0:
            return "", ""

        href = anchor.get_attribute("href") or ""
        if href.startswith("http"):
            detail_url = href
        else:
            detail_url = urljoin(self.config.base_url, href)

        if not detail_url or detail_url.endswith("#"):
            return "", ""

        detail_page = page.context.new_page()
        detail_page.set_default_timeout(self.config.detail_timeout_ms)
        try:
            detail_page.goto(detail_url, wait_until="domcontentloaded")
            detail_page.wait_for_timeout(300)
            detail_text = detail_page.locator("body").inner_text().strip()
            return detail_text, detail_url
        except Exception:  # noqa: BLE001
            return "", detail_url
        finally:
            detail_page.close()
