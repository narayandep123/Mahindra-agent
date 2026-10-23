"""Chat endpoints for the automotive AI assistant."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.agent.agent import run_agent
from app.sessions.store import SessionStore

router = APIRouter(tags=["chat"])
store = SessionStore()
limiter = Limiter(key_func=get_remote_address)


class ChatRequest(BaseModel):
    """Payload for a chat turn."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=1000)


@router.post("/chat")
@limiter.limit("30/minute")
async def chat(request: Request, payload: ChatRequest) -> Any:
    """Stream agent events for a given session and message."""
    async def event_generator() -> Any:
        try:
            async for event in run_agent(payload.session_id, payload.message, store=store):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:
            yield "data: {\"type\":\"error\",\"message\":\"Sorry, something went wrong. Please try again in a moment.\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/session/{session_id}")
async def delete_session(session_id: str) -> dict[str, Any]:
    """Delete a session and reset the conversation context."""
    deleted = await store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True, "deleted": True, "error": None}
