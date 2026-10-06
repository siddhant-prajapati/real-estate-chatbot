from fastapi import APIRouter

router = APIRouter()


@router.get("/live")
async def live() -> dict:
    """Tiny liveness probe for Render (must reply within 5 seconds)."""
    return {"status": "UP"}
