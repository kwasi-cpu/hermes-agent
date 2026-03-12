from collections.abc import AsyncGenerator

from app.models import InternalAuthContext, InternalChatStreamRequest


async def stream_chat(*, auth: InternalAuthContext, req: InternalChatStreamRequest) -> AsyncGenerator[str, None]:
    yield "event: message_start\ndata: {\"conversation_id\": \"%s\", \"request_id\": \"%s\"}\n\n" % (
        req.conversation_id,
        auth.request_id,
    )
    yield "event: delta\ndata: {\"text\": \"Hermes runtime skeleton received your message.\"}\n\n"
    yield "event: delta\ndata: {\"text\": \" Wire your orchestration/tool execution here.\"}\n\n"
    yield "event: message_end\ndata: {\"status\": \"ok\"}\n\n"
