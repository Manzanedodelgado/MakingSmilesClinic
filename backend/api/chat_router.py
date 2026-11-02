"""Chat con LLM streaming - MVP.

Endpoint para chat con streaming SSE.
Browser → SaaS API → Agent Orchestrator → LLMProvider → Ollama
"""
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth_deps import CurrentUser, require_permission
from infrastructure.llm.ollama_provider import get_llm_provider

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    temperature: float = 0.3
    max_tokens: int | None = None


async def stream_chat_response(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int | None = None,
) -> AsyncGenerator[str, None]:
    """Genera streaming SSE para chat."""
    llm_provider = get_llm_provider()
    
    try:
        async for chunk in llm_provider.stream(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        ):
            # Formato SSE
            yield f"data: {chunk}\n\n"
        
        # Fin del stream
        yield "data: [DONE]\n\n"
    except Exception as e:  # raiz: fallo del streaming LLM se reporta por SSE y se relanza
        yield f"data: ERROR: {str(e)}\n\n"
        raise


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    user: CurrentUser = Depends(require_permission("chat.usar")),
):
    """
    Chat streaming con LLM.
    
    Flow:
    Ollama → OllamaProvider → Agent Orchestrator → SaaS API → SSE → Browser
    """
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in request.messages
    ]
    
    return StreamingResponse(
        stream_chat_response(
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/complete")
async def chat_complete(
    request: ChatRequest,
    user: CurrentUser = Depends(require_permission("chat.usar")),
):
    """Chat sin streaming."""
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in request.messages
    ]
    
    llm_provider = get_llm_provider()
    result = await llm_provider.chat(
        messages=messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )
    
    return {
        "response": result.get("message", {}).get("content", ""),
        "provider": llm_provider.provider_name,
        "model": llm_provider.model_name,
    }
