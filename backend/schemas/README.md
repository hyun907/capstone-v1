# 채팅 데이터 계약 읽기

[`chat.py`](chat.py)의 Pydantic 모델은 `/chat`에 들어오는 값과 나가는 값의 모양을 정합니다. 값이 비었거나 공백뿐이면 요청 검증에서 거부합니다.

| 모델 | 필드 | 쓰이는 곳 |
| --- | --- | --- |
| `ChatRequest` | `message`, 선택적 `thread_id` | 사용자가 `/chat`에 보내는 JSON |
| `ChatResponse` | `thread_id`, `message`, `tool_calls` | Backend가 반환하는 JSON |

예를 들어 `{"message":"상태 확인"}`을 보내면 서버가 `thread_id`를 만들고, 응답에 그 ID와 답변을 돌려줍니다. 다음 질문에 같은 ID를 넣으면 대화를 이어갑니다. `tool_calls`에는 **이번 요청**의 도구 이름과 인자가 들어갑니다. 도구를 쓰지 않았다면 빈 목록입니다.

현재 SSE 이벤트 스키마(`stream.py`)는 없습니다. 라우팅이나 스트리밍을 추가할 때는 그 이벤트의 Backend 스키마와 Frontend 타입을 함께 맞춰야 합니다.
