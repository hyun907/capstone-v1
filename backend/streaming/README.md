# 스트리밍 이벤트 읽기

[`event_converter.py`](event_converter.py)의 `convert_langgraph_events()`는 현재 `/chat/stream`에서 단일 Agent의 토큰과 도구 호출을 화면용 이벤트로 바꿉니다. [`sse_formatter.py`](sse_formatter.py)는 이벤트를 `event:`와 `data:` 줄, 빈 줄로 이루어진 SSE 프레임으로 포장합니다.

`convert_supervisor_events()`는 Supervisor의 계획·Task 상태와 중첩 Sub-Agent 이벤트를 변환합니다. 호출할 때 그래프의 `astream(..., stream_mode=["messages", "updates", "custom"], subgraphs=True)`가 필요합니다. `custom` 시작 이벤트와 중첩 메시지의 Task ID 메타데이터를 사용해 병렬 Research 토큰·도구 호출을 해당 Task에 연결합니다. Research 종료 상태는 일괄 갱신되지만 각 Task의 `task_completed`를 따로 보내며 실패에는 안전한 `error_message`를 포함합니다. 최종 답변은 `finalize` 업데이트에서 한 번만 보내며, 정상 종료에만 `done`을 보냅니다. 스트림이 중간에 끊기면 이미 보낸 이벤트를 유지하고 `STREAM_INTERRUPTED` 오류 하나로 종료합니다.

`/chat/stream`은 단일 Agent 변환기를, `/chat/supervisor/stream`은 Supervisor 변환기를 사용합니다. 화면의 Supervisor 카드 연결은 후속 단계입니다.
