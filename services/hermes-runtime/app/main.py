from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse

from app.auth import require_internal_auth
from app.hermes import stream_chat
from app.models import InternalAuthContext, InternalChatStreamRequest

app = FastAPI(title="Sunday Hermes Runtime", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/internal/chat/stream")
async def internal_chat_stream(
    req: InternalChatStreamRequest,
    auth: InternalAuthContext = Depends(require_internal_auth),
) -> StreamingResponse:
    async def event_gen():
        async for chunk in stream_chat(auth=auth, req=req):
            yield chunk

    return StreamingResponse(event_gen(), media_type="text/event-stream")
