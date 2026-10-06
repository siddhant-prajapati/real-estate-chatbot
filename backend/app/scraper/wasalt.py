import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.config import settings
from app.models.property import Property
from app.scraper.base import (
    bedroom_range_from_text,
    clean_text,
    infer_property_type,
    make_property,
    parse_int,
    parse_price,
)

# Wasalt robots.txt disallows /search for generic crawlers. Use public category pages only.
LISTING_PAGES = [
    "https://wasalt.sa/en/properties-for-sale-in-saudi-arabia",
    "https://wasalt.sa/en/villas-for-sale-in-saudi-arabia",
    "https://wasalt.sa/en/apartments-for-sale-in-saudi-arabia",
    "https://wasalt.sa/en/properties-for-sale-in-riyadh",
    "https://wasalt.sa/en/properties-for-rent-in-jeddah",
]


def _is_disallowed(url: str) -> bool:
    path = urlparse(url).path
    return path.startswith("/search")


def _looks_like_listing(url: str, title: str) -> bool:
    if _is_disallowed(url):
        return False
    text = f"{url} {title}".lower()
    return any(token in text for token in ("villa", "apartment", "property", "sqm", "bedroom", "for-sale", "for-rent"))


def _parse_card(card, page_url: str) -> Property | None:
    title_el = card.select_one("h2, h3, h4, a")
    title = clean_text(title_el.get_text(" ")) if title_el else ""
    if not title or len(title) < 8:
        return None
    link_el = card.select_one("a[href]")
    url = page_url
    if link_el and link_el.get("href"):
        href = link_el["href"]
        if href.startswith("http"):
            url = href.split("?")[0]
        elif href.startswith("/"):
            url = f"https://wasalt.sa{href.split('?')[0]}"
    if _is_disallowed(url):
        return None

    text = clean_text(card.get_text(" "))
    location_el = card.select_one("[class*='location'], h6, small")
    location = clean_text(location_el.get_text(" ")) if location_el else ""
    if not location:
        loc_match = re.search(
            r"(Riyadh|Jeddah|Dammam|Khobar|Makkah|Madinah|Abha|Al-[A-Za-z\-]+(?:, [A-Za-z ]+)?)",
            text,
        )
        location = loc_match.group(0) if loc_match else "Saudi Arabia"

    price, currency, price_text = parse_price(text)
    beds, beds_min, beds_max = bedroom_range_from_text(text)
    if beds is None:
        numbers = [parse_int(li.get_text()) for li in card.select("li")]
        numbers = [n for n in numbers if n]
        if numbers:
            beds = numbers[0]
            beds_min = beds_max = beds
    bathrooms = None
    listed_numbers = [parse_int(li.get_text()) for li in card.select("li")]
    listed_numbers = [n for n in listed_numbers if n]
    if len(listed_numbers) >= 2:
        bathrooms = listed_numbers[1]

    area = None
    area_match = re.search(r"([\d.]+)\s*SQM", text, re.IGNORECASE)
    if area_match:
        area = float(area_match.group(1))

    city = None
    for name in ["Riyadh", "Jeddah", "Dammam", "Khobar", "Makkah", "Madinah", "Abha"]:
        if name.lower() in location.lower():
            city = name
            break

    return make_property(
        source="Wasalt",
        title=title,
        location=location,
        city=city,
        country="Saudi Arabia",
        property_type=infer_property_type(title + " " + text),
        bedrooms=beds,
        bedrooms_min=beds_min,
        bedrooms_max=beds_max,
        bathrooms=bathrooms,
        price=price,
        currency=currency or ("SAR" if price else None),
        price_text=price_text or ("Price not published on the listing card" if price is None else None),
        area_sqm=area,
        description=text[:800],
        url=url,
    )


def parse_listing_html(page_url: str, html: str) -> list[Property]:
    soup = BeautifulSoup(html, "lxml")
    properties: list[Property] = []
    seen: set[str] = set()
    cards = soup.select("article, [class*='card'], [class*='property'], li")
    for card in cards:
        item = _parse_card(card, page_url)
        if not item:
            continue
        key = f"{item.title}|{item.location}|{item.price}"
        if key in seen:
            continue
        seen.add(key)
        properties.append(item)

    if len(properties) < 5:
        for link in soup.select("a[href]"):
            title = clean_text(link.get_text(" "))
            href = link.get("href") or page_url
            if not _looks_like_listing(href, title):
                continue
            item = make_property(
                source="Wasalt",
                title=title,
                location="Saudi Arabia",
                country="Saudi Arabia",
                property_type=infer_property_type(title),
                url=href if href.startswith("http") else page_url,
                description=title,
            )
            key = item.title
            if key in seen or len(title) < 12:
                continue
            seen.add(key)
            properties.append(item)
    return properties


def listing_pages_for_query(query: str | None = None) -> list[str]:
    if not query:
        return LISTING_PAGES
    text = query.lower()
    selected: list[str] = []
    if "villa" in text:
        selected.append("https://wasalt.sa/en/villas-for-sale-in-saudi-arabia")
    if any(token in text for token in ("apartment", "bedroom", "flat")):
        selected.append("https://wasalt.sa/en/apartments-for-sale-in-saudi-arabia")
    if "riyadh" in text:
        selected.append("https://wasalt.sa/en/properties-for-sale-in-riyadh")
    if "jeddah" in text:
        selected.append("https://wasalt.sa/en/properties-for-rent-in-jeddah")
        selected.append("https://wasalt.sa/en/properties-for-sale-in-jeddah")
    if "dammam" in text:
        selected.append("https://wasalt.sa/en/properties-for-sale-in-dammam")
    if not selected:
        selected = LISTING_PAGES[:3]
    return list(dict.fromkeys(selected))[:4]


async def scrape_wasalt(max_properties: int | None = None, query: str | None = None) -> list[Property]:
    from app.scraper.fetch import fetch_pages

    limit = max_properties or settings.scrape_max_per_source
    collected: list[Property] = []
    seen: set[str] = set()
    pages = await fetch_pages(listing_pages_for_query(query))
    for listing_url, html in pages.items():
        items = parse_listing_html(listing_url, html)
        for item in items:
            key = f"{item.title}|{item.location}|{item.price}"
            if key in seen:
                continue
            seen.add(key)
            collected.append(item)
            if len(collected) >= limit:
                return collected
    return collected[:limit]
