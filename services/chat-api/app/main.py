from uuid import uuid4

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse

from app.auth import require_auth
from app.config import Settings, get_settings
from app.hermes_client import stream_hermes
from app.models import AuthContext, ChatStreamRequest, InternalChatRequest

app = FastAPI(title="Sunday Chat API", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat/stream")
async def chat_stream(
    req: ChatStreamRequest,
    auth: AuthContext = Depends(require_auth),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    conversation_id = req.conversation_id or uuid4()
    request_id = str(uuid4())

    payload = InternalChatRequest(
        conversation_id=conversation_id,
        message=req.message,
        client_message_id=req.client_message_id,
    )

    async def event_gen():
        async for chunk in stream_hermes(settings=settings, auth=auth, request_id=request_id, payload=payload):
            yield chunk

    return StreamingResponse(event_gen(), media_type="text/event-stream")
