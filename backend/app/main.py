import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.live import router as live_router
from app.config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    boot = asyncio.create_task(_boot_sqlite())
    yield
    if not boot.done():
        boot.cancel()


async def _boot_sqlite() -> None:
    await asyncio.sleep(0)
    from app.services.ingest import ensure_ready

    await asyncio.to_thread(ensure_ready)


app = FastAPI(
    title=settings.app_name,
    description="RAG chatbot over a limited public DarGlobal and Wasalt property dataset.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(live_router, prefix="/api", tags=["health"])


def _register_heavy_routes() -> None:
    from app.api.admin import router as admin_router
    from app.api.chat import router as chat_router
    from app.api.chroma_ui import router as chroma_ui_router
    from app.api.health import router as health_router

    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(chat_router, prefix="/api", tags=["chat"])
    app.include_router(admin_router, prefix="/api", tags=["admin"])
    app.include_router(chroma_ui_router, tags=["chroma"])


_register_heavy_routes()


if settings.frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=settings.frontend_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("chroma"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = settings.frontend_dir / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(settings.frontend_dir / "index.html")
else:

    @app.get("/")
    def root():
        return {
            "name": settings.app_name,
            "docs": "/docs",
            "health": "/api/health",
            "chat": "/api/chat",
        }
