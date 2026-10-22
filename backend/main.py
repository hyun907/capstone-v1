"""ICT 운영 지원 Backend의 HTTP 진입점."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from openai import RateLimitError

from backend.agent.graph import build_agent
from backend.agent.supervisor_graph import build_supervisor_graph
from backend.schemas.chat import ChatRequest, ChatResponse
from backend.schemas.stream import ErrorEvent
from backend.streaming.event_converter import convert_langgraph_events, convert_supervisor_events
from backend.streaming.sse_formatter import format_sse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """단일 Agent와 Supervisor의 대화 메모리를 요청 간 보존합니다."""
    application.state.agent = await build_agent()
    try:
        application.state.supervisor_graph = await build_supervisor_graph()
        yield
    finally:
        del application.state.agent
        if hasattr(application.state, "supervisor_graph"):
            del application.state.supervisor_graph


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["POST"],
    allow_headers=["content-type"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Backend가 요청을 받을 준비를 마쳤는지 확인합니다."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Agent를 실행하고 이번 요청의 답변과 도구 호출만 반환합니다."""
    thread_id = payload.thread_id or str(uuid4())
    result = await request.app.state.agent.ainvoke(
        {"messages": [{"role": "user", "content": payload.message}]},
        {"configurable": {"thread_id": thread_id}},
    )
    messages = result["messages"]
    last_user_index = next(
        (index for index in range(len(messages) - 1, -1, -1) if isinstance(messages[index], HumanMessage)),
        None,
    )
    if last_user_index is None:
        raise RuntimeError("Agent 응답에 현재 사용자 메시지가 없습니다.")

    current_ai_messages = [
        message for message in messages[last_user_index + 1 :] if isinstance(message, AIMessage)
    ]
    if not current_ai_messages or not current_ai_messages[-1].text.strip():
        raise RuntimeError("Agent 응답이 비어 있습니다.")

    tool_calls = [
        {"name": call["name"], "args": call["args"]}
        for message in current_ai_messages
        for call in message.tool_calls
    ]
    return ChatResponse(
        thread_id=thread_id,
        message=current_ai_messages[-1].text.strip(),
        tool_calls=tool_calls,
    )


@app.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    """Agent 진행 상황을 SSE로 차례로 전달합니다."""
    thread_id = payload.thread_id or str(uuid4())

    async def event_generator() -> AsyncIterator[str]:
        graph_stream = request.app.state.agent.astream(
            {"messages": [{"role": "user", "content": payload.message}]},
            {"configurable": {"thread_id": thread_id}},
            stream_mode=["messages", "updates"],
        )
        try:
            async for event in convert_langgraph_events(graph_stream, thread_id):
                yield format_sse(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("스트림 생성 실패: %s", type(exc).__name__)
            if isinstance(exc, RateLimitError):
                if exc.code == "credit_balance_exhausted":
                    yield format_sse(ErrorEvent(
                        code="API_CREDIT_EXHAUSTED",
                        message="OpenAI API 크레딧이 소진되었습니다. API 결제 설정에서 잔액을 확인해 주세요.",
                    ))
                else:
                    yield format_sse(ErrorEvent(
                        code="MODEL_RATE_LIMIT",
                        message="OpenAI 요청 한도에 도달했습니다. 잠시 후 다시 시도하고, 계속되면 API 사용량을 확인해 주세요.",
                    ))
            else:
                yield format_sse(ErrorEvent(
                    code="STREAM_FAILED",
                    message="응답 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
                ))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat/supervisor/stream")
async def chat_supervisor_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    """Supervisor의 계획, 작업 진행, 최종 답변을 SSE로 전달합니다."""
    thread_id = payload.thread_id or str(uuid4())

    async def event_generator() -> AsyncIterator[str]:
        graph_stream = request.app.state.supervisor_graph.astream(
            {"messages": [{"role": "user", "content": payload.message}]},
            {"configurable": {"thread_id": thread_id}},
            stream_mode=["messages", "updates"],
            subgraphs=True,
        )
        async for event in convert_supervisor_events(graph_stream, thread_id):
            yield format_sse(event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
