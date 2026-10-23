# 스트리밍 이벤트 읽기

[`event_converter.py`](event_converter.py)의 `convert_langgraph_events()`는 현재 `/chat/stream`에서 단일 Agent의 토큰과 도구 호출을 화면용 이벤트로 바꿉니다. [`sse_formatter.py`](sse_formatter.py)는 이벤트를 `event:`와 `data:` 줄, 빈 줄로 이루어진 SSE 프레임으로 포장합니다.

`convert_supervisor_events()`는 Supervisor의 계획·Task 상태와 중첩 Sub-Agent 이벤트를 변환합니다. 호출할 때 그래프의 `astream(..., stream_mode=["messages", "updates"], subgraphs=True)`가 필요합니다. `start_task` 업데이트에서 Task ID를 얻고, `execute_task`의 중첩 namespace에 연결해 토큰과 도구 호출을 해당 Task로 표시합니다. Task 종료는 성공과 실패 모두 `task_completed`로 보내되 `status`와 안전한 `error_message`로 구분합니다. 최종 답변은 `finalize` 업데이트에서 한 번만 보내며, 정상 종료에만 `done`을 보냅니다. 스트림이 중간에 끊기면 이미 보낸 이벤트를 유지하고 `STREAM_INTERRUPTED` 오류 하나로 종료합니다.

`/chat/stream`은 단일 Agent 변환기를, `/chat/supervisor/stream`은 Supervisor 변환기를 사용합니다. 화면의 Supervisor 카드 연결은 후속 단계입니다.
