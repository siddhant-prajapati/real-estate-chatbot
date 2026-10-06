import json
import sqlite3
from pathlib import Path

from app.config import settings
from app.models.property import Property


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS properties (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    city TEXT,
    country TEXT,
    property_type TEXT,
    bedrooms INTEGER,
    bedrooms_min INTEGER,
    bedrooms_max INTEGER,
    bathrooms INTEGER,
    price REAL,
    currency TEXT,
    price_text TEXT,
    area_sqm REAL,
    description TEXT,
    amenities TEXT,
    url TEXT NOT NULL,
    status TEXT,
    scraped_at TEXT
)
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(CREATE_SQL)
    return conn


def _row_to_property(row: sqlite3.Row) -> Property:
    data = dict(row)
    data["amenities"] = json.loads(data["amenities"] or "[]")
    return Property.model_validate(data)


def replace_all(properties: list[Property], db_path: Path | None = None) -> int:
    conn = connect(db_path)
    try:
        conn.execute("DELETE FROM properties")
        conn.executemany(
            """
            INSERT INTO properties (
                id, source, title, location, city, country, property_type,
                bedrooms, bedrooms_min, bedrooms_max, bathrooms, price, currency,
                price_text, area_sqm, description, amenities, url, status, scraped_at
            ) VALUES (
                :id, :source, :title, :location, :city, :country, :property_type,
                :bedrooms, :bedrooms_min, :bedrooms_max, :bathrooms, :price, :currency,
                :price_text, :area_sqm, :description, :amenities, :url, :status, :scraped_at
            )
            """,
            [
                {
                    **item.model_dump(exclude={"amenities"}),
                    "amenities": json.dumps(item.amenities),
                }
                for item in properties
            ],
        )
        conn.commit()
        return len(properties)
    finally:
        conn.close()


def list_properties(db_path: Path | None = None) -> list[Property]:
    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM properties ORDER BY source, title").fetchall()
        return [_row_to_property(row) for row in rows]
    finally:
        conn.close()


def get_by_ids(ids: list[str], db_path: Path | None = None) -> list[Property]:
    if not ids:
        return []
    conn = connect(db_path)
    try:
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"SELECT * FROM properties WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        found = {row["id"]: _row_to_property(row) for row in rows}
        return [found[item_id] for item_id in ids if item_id in found]
    finally:
        conn.close()


def upsert_properties(properties: list[Property], db_path: Path | None = None) -> int:
    if not properties:
        return 0
    conn = connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO properties (
                id, source, title, location, city, country, property_type,
                bedrooms, bedrooms_min, bedrooms_max, bathrooms, price, currency,
                price_text, area_sqm, description, amenities, url, status, scraped_at
            ) VALUES (
                :id, :source, :title, :location, :city, :country, :property_type,
                :bedrooms, :bedrooms_min, :bedrooms_max, :bathrooms, :price, :currency,
                :price_text, :area_sqm, :description, :amenities, :url, :status, :scraped_at
            )
            ON CONFLICT(id) DO UPDATE SET
                source=excluded.source,
                title=excluded.title,
                location=excluded.location,
                city=excluded.city,
                country=excluded.country,
                property_type=excluded.property_type,
                bedrooms=excluded.bedrooms,
                bedrooms_min=excluded.bedrooms_min,
                bedrooms_max=excluded.bedrooms_max,
                bathrooms=excluded.bathrooms,
                price=excluded.price,
                currency=excluded.currency,
                price_text=excluded.price_text,
                area_sqm=excluded.area_sqm,
                description=excluded.description,
                amenities=excluded.amenities,
                url=excluded.url,
                status=excluded.status,
                scraped_at=excluded.scraped_at
            """,
            [
                {
                    **item.model_dump(exclude={"amenities"}),
                    "amenities": json.dumps(item.amenities),
                }
                for item in properties
            ],
        )
        conn.commit()
        return len(properties)
    finally:
        conn.close()


def count_properties(db_path: Path | None = None) -> int:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM properties").fetchone()
        return int(row["n"])
    finally:
        conn.close()
