"""Playwright 기반 크롤러.

각 사이트를 방문해서 SiteConfig에 정의된 selector로 행을 읽고,
(사이트명, 공고명, 마감일, 링크) 형태로 정리한다. 마감된 공고는 여기서 걸러낸다.
"""
import re
from datetime import date
from typing import Optional

from playwright.sync_api import ElementHandle, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from .dateutils import extract_deadline_from_title, parse_column_date
from .sites import SiteConfig, SITES

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _build_link_from_onclick(site: SiteConfig, row: ElementHandle) -> Optional[str]:
    el = row.query_selector(site.link_selector) if site.link_selector else row
    if el is None:
        return None
    onclick = el.get_attribute("onclick") or ""

    if site.link_builder == "artskorealab":
        m = re.search(r"goView\('(\d+)'\)", onclick)
        if not m:
            return None
        return f"https://www.artskorealab.kr/bbs/view.do?key=2303300002&pstSn={m.group(1)}"

    if site.link_builder == "sfac":
        m = re.search(r"doView\('(\d+)'\s*,\s*'(\d+)'", onclick)
        if not m:
            return None
        cb_idx, bc_idx = m.group(1), m.group(2)
        return f"https://www.sfac.or.kr/opensquare/notice/support_list.do?cbIdx={cb_idx}&bcIdx={bc_idx}"

    return None


def _build_link(site: SiteConfig, row: ElementHandle) -> Optional[str]:
    if site.link_attr == "onclick":
        return _build_link_from_onclick(site, row)

    el = row.query_selector(site.link_selector) if site.link_selector else row
    if el is None:
        return None
    try:
        href = el.evaluate("el => el.href")
    except Exception:
        href = el.get_attribute("href")
    return href or None


def _clean_title(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"^(N|new|NEW)\s*(?=\d{4}|\[)", "", text)
    text = re.sub(r"^\[(공지|공고|N)\]\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def crawl_site(page: Page, site: SiteConfig) -> list[dict]:
    results: list[dict] = []
    page.goto(site.list_url, wait_until="domcontentloaded", timeout=30000)

    wait_selector = site.wait_selector or site.row_selector
    try:
        page.wait_for_selector(wait_selector, timeout=site.wait_timeout_ms)
    except PlaywrightTimeoutError:
        print(f"[{site.name}] 목록 요소가 시간 내에 나타나지 않음: {wait_selector}")
        return results

    rows = page.query_selector_all(site.row_selector)
    for row in rows:
        try:
            title_el = row.query_selector(site.title_selector) if site.title_selector else row
            if title_el is None:
                continue
            raw_title = title_el.inner_text()
            if not raw_title or not raw_title.strip():
                continue

            if site.title_exclude_pattern and re.search(site.title_exclude_pattern, raw_title.strip()):
                continue

            if site.status_selector:
                status_el = row.query_selector(site.status_selector)
                status_text = (status_el.get_attribute("alt") or "") if status_el else ""
                if site.status_keep_pattern and not re.search(site.status_keep_pattern, status_text):
                    continue

            link = _build_link(site, row)
            if not link:
                continue

            deadline: Optional[date] = None
            if site.deadline_source == "column" and site.deadline_selector:
                date_el = row.query_selector(site.deadline_selector)
                if date_el:
                    deadline = parse_column_date(date_el.inner_text())
            elif site.deadline_source == "title":
                reference_date = date.today()
                if site.posted_date_selector:
                    posted_el = row.query_selector(site.posted_date_selector)
                    if posted_el:
                        parsed_ref = parse_column_date(posted_el.inner_text())
                        if parsed_ref:
                            reference_date = parsed_ref
                deadline = extract_deadline_from_title(raw_title, reference_date)

            results.append(
                {
                    "site": site.name,
                    "title": _clean_title(raw_title),
                    "deadline": deadline,
                    "link": link,
                }
            )
        except Exception as e:  # noqa: BLE001 - 한 행 실패가 전체 크롤링을 막지 않도록
            print(f"[{site.name}] 행 파싱 실패: {e}")
            continue

    return results


def crawl_all(sites: Optional[list[SiteConfig]] = None, headless: bool = True) -> list[dict]:
    target_sites = sites if sites is not None else [s for s in SITES if s.enabled]
    all_results: list[dict] = []
    today = date.today()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="ko-KR",
        )
        page = context.new_page()

        for site in target_sites:
            print(f"=== {site.name} 크롤링 시작 ({site.list_url}) ===")
            try:
                rows = crawl_site(page, site)
            except Exception as e:  # noqa: BLE001
                print(f"[{site.name}] 크롤링 실패: {e}")
                rows = []

            open_rows = [r for r in rows if r["deadline"] is None or r["deadline"] >= today]
            closed_count = len(rows) - len(open_rows)
            print(
                f"[{site.name}] 총 {len(rows)}건 수집, 마감 {closed_count}건 제외, "
                f"최종 {len(open_rows)}건"
            )
            all_results.extend(open_rows)

        browser.close()

    skipped = [s for s in (sites if sites is not None else SITES) if not s.enabled]
    for s in skipped:
        print(f"[{s.name}] 비활성화됨 (건너뜀): {s.notes}")

    return all_results
