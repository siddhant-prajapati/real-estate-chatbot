import re

from app.llm.openrouter import complete
from app.models.property import ChatResponse, Property, PropertySource
from app.rag.retriever import retrieve
from app.services.ingest import ensure_ready
from app.services.live_refresh import needs_live_scrape, refresh_from_websites

IDENTITY_ANSWER = "I'm a real-estate assistant for DarGlobal and Wasalt."
_IDENTITY_MESSAGES = {
    "who are you",
    "who r you",
    "who r u",
    "who are u",
    "what are you",
    "whats your name",
    "what is your name",
    "who is this",
    "introduce yourself",
    "tell me about yourself",
    "what do you do",
    "what can you do",
    "who are you and what do you do",
}


def is_identity_question(question: str) -> bool:
    text = question.lower().strip()
    text = re.sub(r"^(hi|hello|hey)[,!\s]+", "", text)
    text = re.sub(r"[?!.,\"'`’]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text in _IDENTITY_MESSAGES


def to_source(item: Property) -> PropertySource:
    return PropertySource(
        id=item.id,
        title=item.title,
        source=item.source,
        url=item.url,
        location=item.location,
        property_type=item.property_type,
        bedrooms=item.bedroom_range(),
        bathrooms=str(item.bathrooms) if item.bathrooms is not None else None,
        price=item.formatted_price(),
        area_sqm=item.area_sqm,
        status=item.status,
        amenities=item.amenities,
    )


def _brief(text: str, limit: int = 120) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    cut = value[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def format_context(properties: list[Property]) -> str:
    if not properties:
        return "No matching properties were retrieved."
    blocks = []
    for index, item in enumerate(properties, start=1):
        note = _brief(item.description)
        line = (
            f"{index}. {item.title} | {item.source} | {item.location} | "
            f"{item.property_type or 'Property'} | {item.bedroom_range()} bed | "
            f"{item.formatted_price()}"
        )
        if note:
            line += f" | {note}"
        blocks.append(line)
    return "\n".join(blocks)


_FLUFF_INTRO = re.compile(
    r"(?i)^(here are|i found|i have found|based on|from the|these are|below are)\b"
)


def _compact_listing(block: str) -> str:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        return ""
    title = lines[0]
    location = None
    price = None
    for line in lines[1:]:
        lower = line.lower()
        if any(token in lower for token in ("http", "www.", "amenit", "url", "view listing")):
            continue
        if re.match(r"(?i)^\**status\**", line):
            continue
        line = re.split(r"(?i)\s*[·|\-]\s*\**status\**", line, maxsplit=1)[0].strip(" ·-|")
        if re.search(r"(?i)price", line) and price is None:
            price = line
        elif location is None:
            location = line
    kept = [title]
    if location:
        kept.append(location)
    if price:
        kept.append(price)
    return "\n".join(kept[:3])


def compact_answer(text: str, max_listings: int = 3) -> str:
    text = (text or "").strip()
    if not text:
        return text
    heading = re.search(r"(?m)^### ", text)
    if not heading:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return " ".join(sentences[:2]).strip()
    intro = text[: heading.start()].strip()
    rest = text[heading.start() :].strip()
    listings = [
        chunk.strip()
        for chunk in re.split(r"(?=^### )", rest, flags=re.M)
        if chunk.strip().startswith("###")
    ][:max_listings]
    if intro:
        intro = re.split(r"(?<=[.!?])\s+", intro, maxsplit=1)[0].strip()
        if (
            _FLUFF_INTRO.match(intro)
            or re.match(r"(?i)^(we need to|let's|the rule|we must|write the final)", intro)
            or len(intro.split()) > 18
        ):
            intro = ""
    parts: list[str] = []
    if intro:
        parts.append(intro)
    parts.extend(filter(None, (_compact_listing(item) for item in listings)))
    return "\n\n".join(parts).strip() or rest


def looks_like_reasoning(text: str) -> bool:
    return bool(
        re.match(
            r"(?i)^(we need to|let's|the rule|we must|write the final|one short sentence|we have )",
            (text or "").strip(),
        )
    )


def fallback_answer(question: str, properties: list[Property]) -> str:
    if not properties:
        return (
            "I could not find matching information in the stored DarGlobal and Wasalt listings."
        )
    lines: list[str] = []
    for item in properties[:3]:
        lines.extend(
            [
                f"### {item.title}",
                f"**{item.location}** · {item.property_type or 'Property'} · {item.bedroom_range()} bedrooms",
                f"**{item.formatted_price()}**",
                "",
            ]
        )
    return "\n".join(lines)


async def answer_question(question: str) -> ChatResponse:
    if is_identity_question(question):
        return ChatResponse(
            answer=IDENTITY_ANSWER,
            sources=[],
            model=None,
            used_fallback=False,
            live_scrape_attempted=False,
            new_listings=0,
            scrape_note=None,
        )

    ensure_ready()
    properties = retrieve(question)
    scrape = None
    if needs_live_scrape(question, properties):
        scrape = await refresh_from_websites(question)
        if scrape.new_listings:
            properties = retrieve(question)

    shown = properties[:3]
    context = format_context(shown)
    prompt = (
        f"User question:\n{question}\n\n"
        f"Listings:\n{context}\n\n"
        "Final answer only. At most 3 properties. No amenities, URLs, or extra commentary."
    )

    try:
        text, model = await complete(prompt)
        answer = compact_answer(text)
        if looks_like_reasoning(answer) or not answer:
            answer = fallback_answer(question, shown)
        return ChatResponse(
            answer=answer,
            sources=[to_source(item) for item in shown],
            model=model,
            used_fallback=False,
            live_scrape_attempted=bool(scrape and scrape.attempted),
            new_listings=scrape.new_listings if scrape else 0,
            scrape_note=None,
        )
    except Exception:
        return ChatResponse(
            answer=fallback_answer(question, shown),
            sources=[to_source(item) for item in shown],
            model=None,
            used_fallback=True,
            live_scrape_attempted=bool(scrape and scrape.attempted),
            new_listings=scrape.new_listings if scrape else 0,
            scrape_note=None,
        )
