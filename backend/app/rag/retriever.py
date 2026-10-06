import re

from app.config import settings
from app.db.sqlite import get_by_ids, list_properties
from app.models.property import Property

TO_AED = {
    "AED": 1.0,
    "SAR": 0.98,
    "USD": 3.67,
    "GBP": 4.70,
    "EUR": 4.00,
    "QAR": 1.01,
    "OMR": 9.54,
}


class QueryFilters(dict):
    pass


def parse_filters(question: str) -> QueryFilters:
    text = question.lower()
    filters = QueryFilters()

    bed_match = re.search(r"(\d+)\s*(?:bed|br|bedroom)", text)
    if bed_match:
        filters["bedrooms"] = int(bed_match.group(1))

    if "studio" in text:
        filters["bedrooms"] = 0

    price_match = re.search(
        r"(?:under|below|less than|upto|up to)\s*(?:aed|sar|usd|gbp)?\s*([\d.,]+)\s*(million|mn|m|k)?",
        text,
    )
    if price_match:
        amount = float(price_match.group(1).replace(",", ""))
        suffix = (price_match.group(2) or "").lower()
        if suffix in {"million", "mn", "m"}:
            amount *= 1_000_000
        elif suffix == "k":
            amount *= 1_000
        currency = "AED"
        if "sar" in text or "riyal" in text:
            currency = "SAR"
        filters["max_price_aed"] = amount * TO_AED.get(currency, 1.0)

    if "darglobal" in text or "dar global" in text:
        filters["source"] = "DarGlobal"
    if "wasalt" in text:
        filters["source"] = "Wasalt"

    for label, needles in {
        "Villa": ["villa", "villas", "mansion"],
        "Apartment": ["apartment", "apartments", "flat", "residence", "residences"],
        "Penthouse": ["penthouse"],
        "Hotel": ["hotel"],
    }.items():
        if any(needle in text for needle in needles):
            filters["property_type"] = label
            break

    for city in ["dubai", "riyadh", "jeddah", "doha", "london", "muscat", "benahavís", "benahavis", "makkah"]:
        if city in text:
            filters["city"] = city.replace("benahavis", "benahavís")
            break

    for country, needles in {
        "United Arab Emirates": ["uae", "united arab emirates"],
        "Saudi Arabia": ["saudi", "ksa"],
        "Qatar": ["qatar"],
        "Oman": ["oman"],
        "Spain": ["spain"],
        "United Kingdom": ["london", "uk", "united kingdom"],
        "Maldives": ["maldives"],
    }.items():
        if any(needle in text for needle in needles):
            filters["country"] = country
            break

    amenity_map = {
        "pool": ["pool", "swimming"],
        "gym": ["gym", "fitness"],
        "golf": ["golf"],
        "beach": ["beach"],
        "cinema": ["cinema"],
        "concierge": ["concierge"],
        "sea view": ["sea view", "sea-view", "ocean view"],
    }
    amenities = [name for name, needles in amenity_map.items() if any(needle in text for needle in needles)]
    if amenities:
        filters["amenities"] = amenities
    return filters


def _price_in_aed(item: Property) -> float | None:
    if item.price is None:
        return None
    return item.price * TO_AED.get((item.currency or "AED").upper(), 1.0)


def _matches_bedrooms(item: Property, bedrooms: int) -> bool:
    if item.bedrooms_min is not None and item.bedrooms_max is not None:
        return item.bedrooms_min <= bedrooms <= item.bedrooms_max
    if item.bedrooms is not None:
        return item.bedrooms == bedrooms
    return False


def score_property(item: Property, question: str, filters: QueryFilters, distance: float | None) -> float:
    score = 1.0 - float(distance if distance is not None else 1.0)
    haystack = " ".join(
        [
            item.title,
            item.location or "",
            item.city or "",
            item.description,
            " ".join(item.amenities),
        ]
    ).lower()
    question_terms = {token for token in re.findall(r"[a-z0-9]+", question.lower()) if len(token) > 3}
    stop = {"show", "find", "tell", "about", "which", "what", "have", "from", "with", "under", "properties", "property"}
    overlap = question_terms - stop
    score += 0.08 * sum(1 for token in overlap if token in haystack)

    if filters.get("source") and item.source.lower() == filters["source"].lower():
        score += 0.25
    elif filters.get("source"):
        score -= 0.4
    if filters.get("city") and filters["city"] in f"{item.city or ''} {item.location or ''}".lower():
        score += 0.2
    elif filters.get("city"):
        score -= 0.35
    if filters.get("country") and filters["country"].lower() in (item.country or "").lower():
        score += 0.1
    if filters.get("property_type") and (item.property_type or "").lower() == filters["property_type"].lower():
        score += 0.2
    elif filters.get("property_type") and filters["property_type"].lower() not in f"{item.property_type or ''} {item.title}".lower():
        score -= 0.2
    if filters.get("bedrooms") is not None:
        if _matches_bedrooms(item, filters["bedrooms"]):
            score += 0.25
        else:
            score -= 0.25
    if filters.get("max_price_aed") is not None:
        price = _price_in_aed(item)
        if price is None:
            score -= 0.05
        elif price <= filters["max_price_aed"]:
            score += 0.3
        else:
            score -= 0.45
    for amenity in filters.get("amenities", []):
        if amenity in haystack or amenity.replace(" ", "") in haystack.replace(" ", ""):
            score += 0.2
    return score


def retrieve(question: str, k: int | None = None) -> list[Property]:
    limit = k or settings.retrieve_k
    filters = parse_filters(question)
    properties = list_properties()
    ranked_ids: list[tuple[str, float]] = []
    try:
        from app.rag.vector_store import query_ids

        ranked_ids = query_ids(question, n_results=max(limit * 4, 24))
    except Exception:
        ranked_ids = []
    distance_map = {item_id: distance for item_id, distance in ranked_ids}
    if not properties:
        properties = get_by_ids([item_id for item_id, _ in ranked_ids])
    scored = sorted(
        properties,
        key=lambda item: score_property(item, question, filters, distance_map.get(item.id)),
        reverse=True,
    )
    if filters.get("city"):
        city = filters["city"]
        matching = [
            item
            for item in scored
            if city in f"{item.city or ''} {item.location or ''}".lower()
        ]
        if matching:
            scored = matching
    if filters.get("source"):
        matching = [item for item in scored if item.source.lower() == filters["source"].lower()]
        if matching:
            scored = matching
    return scored[:limit]
