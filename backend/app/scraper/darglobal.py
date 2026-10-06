import asyncio
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.config import settings
from app.models.property import Property
from app.scraper.base import (
    USER_AGENT,
    bedroom_range_from_text,
    clean_text,
    infer_property_type,
    make_property,
    parse_int,
    unique_links,
)

LISTING_URL = "https://darglobal.co.uk/projects"
ALLOWED_HOSTS = {"darglobal.co.uk", "www.darglobal.co.uk"}
SKIP_PATHS = {
    "/projects",
    "/about",
    "/press",
    "/blog",
    "/get-in-touch",
    "/investor",
    "/hospitality",
    "/commercial",
    "/partner",
    "/terms-of-uses",
    "/privacy-policy",
}


def _is_project_url(url: str) -> bool:
    path = urlparse(url).path.rstrip("/")
    if not path or path in SKIP_PATHS:
        return False
    if any(part in path for part in ("/category/", "/product-category/", "/blog/", "/press/", "/wp-")):
        return False
    if path.startswith("/projects/") and path != "/projects":
        return True
    parts = [part for part in path.split("/") if part]
    return len(parts) == 1


def _parse_spec_map(text: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    patterns = {
        "property_type": r"Property Type\s+([^\n]+)",
        "status": r"Status\s+([^\n]+)",
        "stage": r"Stage\s+([^\n]+)",
        "units": r"Unit(?:s| Type| type)\s+([^\n]+)",
        "area": r"Area[^\n]{0,20}\s+([0-9].+)",
        "completion": r"(?:Expected Completion Date|Completion Date)\s+([^\n]+)",
        "location": r"Location\s+([^\n]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            specs[key] = clean_text(match.group(1))
    return specs


def _amenities_from_text(text: str) -> list[str]:
    labels = [
        "Infinity Pool",
        "Swimming Pool",
        "Gym",
        "Yoga",
        "Concierge",
        "Cinema",
        "Golf",
        "Private Beach",
        "Spa",
        "Kids Pool",
        "Parking",
        "Sea Views",
        "Clubhouse",
    ]
    found = []
    lower = text.lower()
    for label in labels:
        if label.lower() in lower:
            found.append(label)
    return found


def parse_project_page(url: str, html: str) -> Property | None:
    soup = BeautifulSoup(html, "lxml")
    title = clean_text(soup.title.get_text() if soup.title else "")
    heading = soup.select_one("h1")
    if heading:
        title = clean_text(heading.get_text()) or title
    title = re.sub(r"\s*\|\s*DarGlobal.*$", "", title, flags=re.IGNORECASE)
    if not title:
        return None

    paragraph = " ".join(clean_text(p.get_text(" ")) for p in soup.select("p")[:8])
    body = clean_text(soup.get_text("\n"))
    specs = _parse_spec_map(body)
    location = specs.get("location")
    if not location:
        location_el = soup.select_one("h1 + p, h1 + div, .location")
        location = clean_text(location_el.get_text(" ")) if location_el else ""
    if not location:
        loc_match = re.search(r"([A-Za-z][A-Za-z\s,|]+(?:UAE|United Arab Emirates|Spain|Qatar|Oman|United Kingdom|Saudi Arabia|Maldives))", body)
        location = clean_text(loc_match.group(1)) if loc_match else "Not specified"

    beds, beds_min, beds_max = bedroom_range_from_text(specs.get("units", "") + " " + body[:2000])
    area = None
    if specs.get("area"):
        area = float(parse_int(specs["area"]) or 0) or None

    city = location.split(",")[0].strip() if location else None
    country = None
    for name in ["United Arab Emirates", "UAE", "Spain", "Qatar", "Oman", "United Kingdom", "Saudi Arabia", "Maldives"]:
        if name.lower() in location.lower() or name.lower() in body[:1500].lower():
            country = "United Arab Emirates" if name in {"UAE", "United Arab Emirates"} else name
            break

    return make_property(
        source="DarGlobal",
        title=title,
        location=location or "Not specified",
        city=city,
        country=country,
        property_type=infer_property_type(specs.get("property_type", "") + " " + title + " " + paragraph) or specs.get("property_type"),
        bedrooms=beds,
        bedrooms_min=beds_min,
        bedrooms_max=beds_max,
        area_sqm=area,
        description=paragraph[:1200] or body[:1200],
        amenities=_amenities_from_text(body),
        url=url,
        status=specs.get("status") or specs.get("stage"),
        price_text="Price on request" if "price" not in body.lower()[:4000] else None,
        currency="AED" if (country in {"United Arab Emirates"} or "dubai" in location.lower()) else None,
    )


async def scrape_darglobal(max_properties: int | None = None, query: str | None = None) -> list[Property]:
    from app.scraper.fetch import fetch_pages

    limit = max_properties or settings.scrape_max_per_source
    listing_pages = await fetch_pages([LISTING_URL])
    listing_html = listing_pages.get(LISTING_URL)
    if not listing_html:
        return []

    soup = BeautifulSoup(listing_html, "lxml")
    project_urls = [url for url in unique_links(LISTING_URL, soup, ALLOWED_HOSTS) if _is_project_url(url)]
    if query:
        needles = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 3]
        ranked = []
        for url in project_urls:
            score = sum(1 for token in needles if token in url.lower())
            ranked.append((score, url))
        project_urls = [url for score, url in sorted(ranked, reverse=True)]
    project_urls = project_urls[:limit]

    detail_pages = await fetch_pages(project_urls)
    properties: list[Property] = []
    for url in project_urls:
        html = detail_pages.get(url)
        if not html:
            continue
        item = parse_project_page(url, html)
        if item:
            properties.append(item)
        await asyncio.sleep(0.15)
    return properties
