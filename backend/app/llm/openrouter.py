import httpx

from app.config import settings

SYSTEM_PROMPT = """You are a real-estate assistant for DarGlobal and Wasalt.

Identity questions: reply only with I'm a real-estate assistant for DarGlobal and Wasalt.

Use only the provided listings. Never invent prices, locations, bedrooms, or availability.
Missing price: Price on request. If nothing matches, one sentence and stop.

Write the final answer only. Do not explain your reasoning.

Format:
One short sentence.
### Property Name
**Location** · Type · Bedrooms
**Price**

At most 3 properties. No amenities, URLs, status, or follow-up questions.
"""


async def complete(user_prompt: str) -> tuple[str, str]:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 400,
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_referer,
        "X-Title": settings.openrouter_title,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
    content = data["choices"][0]["message"]["content"]
    model = data.get("model") or settings.openrouter_model
    return content, model
