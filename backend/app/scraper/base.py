import hashlib
import re
from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.models.property import Property

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def slug_id(source: str, url: str, title: str) -> str:
    raw = f"{source}|{url}|{title}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d+)", value.replace(",", ""))
    return int(match.group(1)) if match else None


def parse_price(text: str | None) -> tuple[float | None, str | None, str | None]:
    if not text:
        return None, None, None
    normalized = clean_text(text)
    currency = None
    upper = normalized.upper()
    if "AED" in upper or "DHS" in upper or "DIRHAM" in upper:
        currency = "AED"
    elif "SAR" in upper or "SR" in upper or "RIYAL" in upper:
        currency = "SAR"
    elif "USD" in upper or "$" in normalized:
        currency = "USD"
    elif "GBP" in upper or "£" in normalized:
        currency = "GBP"
    elif "EUR" in upper or "€" in normalized:
        currency = "EUR"
    elif "QAR" in upper:
        currency = "QAR"
    elif "OMR" in upper:
        currency = "OMR"

    amount = None
    million = re.search(r"([\d]+(?:[.,]\d+)?)\s*(?:MILLION|MN|M)\b", upper)
    thousand = re.search(r"([\d]+(?:[.,]\d+)?)\s*K\b", upper)
    plain = re.search(r"([\d]{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|[\d]+(?:[.,]\d+)?)")
    if million:
        amount = float(million.group(1).replace(",", "")) * 1_000_000
    elif thousand:
        amount = float(thousand.group(1).replace(",", "")) * 1_000
    elif plain:
        raw_number = plain.group(1)
        if "," in raw_number and "." in raw_number:
            raw_number = raw_number.replace(",", "")
        elif raw_number.count(",") == 1 and len(raw_number.split(",")[1]) <= 2:
            raw_number = raw_number.replace(",", ".")
        else:
            raw_number = raw_number.replace(",", "")
        try:
            amount = float(raw_number)
        except ValueError:
            amount = None
    return amount, currency, normalized or None


def infer_property_type(text: str) -> str | None:
    lower = text.lower()
    mapping = [
        ("penthouse", "Penthouse"),
        ("villa", "Villa"),
        ("mansion", "Villa"),
        ("townhouse", "Townhouse"),
        ("apartment", "Apartment"),
        ("residence", "Apartment"),
        ("hotel", "Hotel"),
        ("studio", "Apartment"),
        ("land", "Land"),
    ]
    for needle, label in mapping:
        if needle in lower:
            return label
    return None


def bedroom_range_from_text(text: str) -> tuple[int | None, int | None, int | None]:
    matches = [int(value) for value in re.findall(r"(\d+)\s*(?:bed|br|bedroom)", text.lower())]
    studio = bool(re.search(r"\bstudio", text.lower()))
    if studio:
        matches = [0] + matches
    if not matches:
        return None, None, None
    return matches[0], min(matches), max(matches)


def make_property(**kwargs) -> Property:
    kwargs.setdefault("scraped_at", date.today().isoformat())
    if not kwargs.get("id"):
        kwargs["id"] = slug_id(kwargs.get("source", "unknown"), kwargs.get("url", ""), kwargs.get("title", ""))
    return Property.model_validate(kwargs)


def unique_links(base_url: str, soup: BeautifulSoup, allowed_hosts: set[str] | None = None) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    host = urlparse(base_url).netloc
    allowed = allowed_hosts or {host}
    for tag in soup.select("a[href]"):
        href = tag.get("href")
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        url = urljoin(base_url, href).split("?")[0].rstrip("/")
        parsed = urlparse(url)
        if parsed.netloc not in allowed:
            continue
        if url in seen:
            continue
        seen.add(url)
        found.append(url)
    return found
