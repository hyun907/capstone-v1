"""ICT 운영 지원 Backend의 HTTP 진입점."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from langchain_core.messages import AIMessage, HumanMessage

from backend.agent.graph import build_agent
from backend.schemas.chat import ChatRequest, ChatResponse


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """대화 메모리를 보존할 Agent를 프로세스 시작 시 한 번 준비합니다."""
    application.state.agent = await build_agent()
    try:
        yield
    finally:
        del application.state.agent


app = FastAPI(lifespan=lifespan)


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
