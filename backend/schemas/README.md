# 채팅 데이터 계약 읽기

[`chat.py`](chat.py)의 Pydantic 모델은 `/chat`에 들어오는 값과 나가는 값의 모양을 정합니다. 값이 비었거나 공백뿐이면 요청 검증에서 거부합니다.

| 모델 | 필드 | 쓰이는 곳 |
| --- | --- | --- |
| `ChatRequest` | `message`, 선택적 `thread_id` | 사용자가 `/chat`, `/chat/stream`, `/chat/supervisor/stream`에 보내는 JSON |
| `ChatResponse` | `thread_id`, `message`, `tool_calls` | Backend가 반환하는 JSON |

예를 들어 `{"message":"상태 확인"}`을 보내면 서버가 `thread_id`를 만들고, 응답에 그 ID와 답변을 돌려줍니다. 다음 질문에 같은 ID를 넣으면 대화를 이어갑니다. `tool_calls`에는 **이번 요청**의 도구 이름과 인자가 들어갑니다. 도구를 쓰지 않았다면 빈 목록입니다.

[`stream.py`](stream.py)는 `/chat/stream`의 토큰·도구 진행·완료·오류 이벤트와 `/chat/supervisor/stream`의 계획·작업·Sub-Agent 이벤트를 정의합니다. 화면의 Supervisor 카드 연결은 아직 후속 단계입니다. SSE 필드를 바꾸면 [`frontend/lib/types.ts`](../../frontend/lib/types.ts)의 타입도 함께 맞춥니다.

[`error.py`](error.py)의 `CapstoneError`는 내부 원인(`message`)과 화면에 보여 줄 안내(`user_message`)를 분리하는 데이터 모델입니다. 실제 예외 전파에는 `ToolError`·`OrchestrationError`를 사용하고, [`classification.py`](../error_handling/classification.py)가 예외를 오류 코드와 복구 가능성으로 분류합니다. Data는 데이터 조회 실패, Tool은 MCP 연결·호출 실패, Orchestration은 계획·Task·응답 실패, Application은 HTTP/SSE 전달 실패, Presentation은 표시 실패를 책임집니다. Tool의 timeout만 재시도 대상이며, Task 실패를 부분 결과로 처리하는 흐름은 후속 단계에서 연결합니다.

`stream.py`의 기존 `API_CREDIT_EXHAUSTED`, `MODEL_RATE_LIMIT`, `STREAM_FAILED` 코드를 유지하고 Supervisor 스트림 중단용 `STREAM_INTERRUPTED`를 추가했습니다. `error.recoverable=true`는 화면이 이미 받은 부분 결과를 보존할 수 있음을 뜻합니다. Task 실패는 스트림 중단과 달리 `task_completed(status=failed)`로 전달합니다. 화면으로 보낼 때는 `user_message`만 사용해야 하며, 내부 `message`나 예외 문자열을 SSE에 복사하지 않습니다. 단일 Agent의 기존 오류 처리도 그대로 유지됩니다.
