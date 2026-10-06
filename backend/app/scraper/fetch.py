import asyncio

import httpx

from app.config import settings
from app.scraper.base import USER_AGENT


def looks_usable(html: str | None) -> bool:
    if not html or len(html) < 800:
        return False
    lower = html.lower()
    blocked = (
        "cf-mitigated",
        "just a moment",
        "attention required",
        "enable javascript",
        "cloudflare",
    )
    if any(token in lower for token in blocked) and "property" not in lower and "project" not in lower:
        return False
    return True


async def fetch_with_httpx(urls: list[str], timeout_seconds: float = 20) -> dict[str, str]:
    pages: dict[str, str] = {}
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=timeout_seconds) as client:
        for url in urls:
            try:
                response = await client.get(url)
                if response.status_code < 400 and looks_usable(response.text):
                    pages[url] = response.text
            except Exception:
                continue
    return pages


async def fetch_with_playwright(urls: list[str], timeout_ms: int = 25000) -> dict[str, str]:
    from playwright.async_api import async_playwright

    pages: dict[str, str] = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page(user_agent=USER_AGENT)
        for url in urls:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(2500)
                html = await page.content()
                if looks_usable(html):
                    pages[url] = html
            except Exception:
                continue
            await asyncio.sleep(0.3)
        await browser.close()
    return pages


async def fetch_pages(urls: list[str], timeout_seconds: float = 20) -> dict[str, str]:
    unique_urls = list(dict.fromkeys(urls))
    pages = await fetch_with_httpx(unique_urls, timeout_seconds=timeout_seconds)
    missing = [url for url in unique_urls if url not in pages]
    if missing and settings.live_scrape_use_playwright:
        try:
            pages.update(await fetch_with_playwright(missing, timeout_ms=int(timeout_seconds * 1000)))
        except Exception:
            pass
    return pages
