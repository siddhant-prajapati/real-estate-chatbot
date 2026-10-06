from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]
if (BACKEND_DIR / "frontend" / "dist").exists():
    ROOT_DIR = BACKEND_DIR
elif (BACKEND_DIR.parent / "frontend").exists():
    ROOT_DIR = BACKEND_DIR.parent
else:
    ROOT_DIR = BACKEND_DIR

load_dotenv(ROOT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Real Estate AI Chatbot"
    openrouter_api_key: str = ""
    openrouter_model: str = "thinkingmachines/inkling:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_referer: str = "https://real-estate-ai-chatbot.onrender.com"
    openrouter_title: str = "Real Estate AI Chatbot"

    admin_token: str = ""
    embedding_model: str = "chroma-cloud-qwen"
    retrieve_k: int = 5
    scrape_max_per_source: int = 50
    enable_live_scrape: bool = True
    live_scrape_use_playwright: bool = True
    live_scrape_max_per_source: int = 12
    live_scrape_cooldown_seconds: int = 90

    data_dir: Path = BACKEND_DIR / "data"
    chroma_api_key: str = ""
    chroma_tenant: str = "7ff33401-8f97-45e9-92ca-060ca2fdb321"
    chroma_database: str = "real-estate"
    chroma_host: str = "api.trychroma.com"
    chroma_port: int = 8000
    chroma_cloud_timeout_seconds: float = 2.0
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cors_origin_regex: str = r"https://.*\.vercel\.app"
    frontend_dir: Path = ROOT_DIR / "frontend" / "dist"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "properties.db"

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def uses_chroma_cloud(self) -> bool:
        return bool(self.chroma_api_key)

    @property
    def uses_chroma_server(self) -> bool:
        host = (self.chroma_host or "").strip()
        if not host or self.uses_chroma_cloud:
            return False
        return host not in {"api.trychroma.com"}

    @property
    def seed_path(self) -> Path:
        packaged = BACKEND_DIR / "data" / "seed" / "properties.json"
        if packaged.exists():
            return packaged
        return self.data_dir / "seed" / "properties.json"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
