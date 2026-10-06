from fastapi import APIRouter

from app.models.property import ChatRequest, ChatResponse
from app.services.chatbot import answer_question

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    return await answer_question(payload.message.strip())
