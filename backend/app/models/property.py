from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class Property(BaseModel):
    id: str
    source: str
    title: str
    location: str
    city: Optional[str] = None
    country: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    bedrooms_min: Optional[int] = None
    bedrooms_max: Optional[int] = None
    bathrooms: Optional[int] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    price_text: Optional[str] = None
    area_sqm: Optional[float] = None
    description: str = ""
    amenities: list[str] = Field(default_factory=list)
    url: str
    status: Optional[str] = None
    scraped_at: str = Field(default_factory=lambda: date.today().isoformat())

    def bedroom_range(self) -> str:
        if (
            self.bedrooms_min is not None
            and self.bedrooms_max is not None
            and self.bedrooms_min != self.bedrooms_max
        ):
            return f"{self.bedrooms_min}-{self.bedrooms_max}"
        if self.bedrooms is not None:
            return str(self.bedrooms)
        if self.bedrooms_min is not None:
            return str(self.bedrooms_min)
        return "Not specified"

    def formatted_price(self) -> str:
        if self.price_text:
            return self.price_text
        if self.price is None:
            return "Price on request"
        currency = self.currency or ""
        amount = f"{self.price:,.0f}"
        return f"{currency} {amount}".strip()

    def embedding_text(self) -> str:
        amenity_text = ", ".join(self.amenities) if self.amenities else "not listed"
        beds = self.bedroom_range()
        return (
            f"{self.title}. Source: {self.source}. "
            f"Location: {self.location}. City: {self.city or 'unknown'}. "
            f"Country: {self.country or 'unknown'}. "
            f"Property type: {self.property_type or 'unknown'}. "
            f"Bedrooms: {beds}. Bathrooms: {self.bathrooms or 'not specified'}. "
            f"Price: {self.formatted_price()}. "
            f"Area: {self.area_sqm or 'not specified'} sqm. "
            f"Status: {self.status or 'not specified'}. "
            f"Amenities: {amenity_text}. "
            f"Description: {self.description}"
        )


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class PropertySource(BaseModel):
    id: str
    title: str
    source: str
    url: str
    location: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[str] = None
    bathrooms: Optional[str] = None
    price: Optional[str] = None
    area_sqm: Optional[float] = None
    status: Optional[str] = None
    amenities: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    sources: list[PropertySource]
    model: Optional[str] = None
    used_fallback: bool = False
    live_scrape_attempted: bool = False
    new_listings: int = 0
    scrape_note: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    properties: int = 0
    vector_store: str = "unknown"
    llm: str = "unknown"
    live_scrape: str = "unknown"
