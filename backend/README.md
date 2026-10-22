# Backend 읽기

이 폴더는 HTTP 요청을 받아 Agent에 전달하고, JSON 또는 SSE 스트림으로 응답하는 곳입니다.

## 질문 한 번의 흐름

```text
POST /chat → ChatRequest 검사 → thread_id 준비 → Agent 실행
           → 이번 질문의 마지막 답변과 도구 호출 추출 → ChatResponse 반환
```

1. [`main.py`](main.py)의 `lifespan()`이 서버 시작 시 단일 Agent와 Supervisor를 각각 한 번 만듭니다. 이때 MCP 도구도 찾습니다.
2. `chat()`은 질문과 `thread_id`를 받습니다. ID를 생략하면 새 UUID를 만듭니다.
3. Agent에 질문을 전달한 뒤, **이번 요청**에서 나온 마지막 AI 답변과 도구 호출만 응답에 담습니다.
4. 같은 `thread_id`로 다시 요청하면 같은 서버 프로세스의 대화 메모리를 사용합니다. 서버를 재시작하면 이 메모리는 사라집니다.

`GET /health`는 준비된 서버에서 `{"status":"ok"}`를 반환합니다. Agent나 도구 실행이 실패하면 현재 `/chat` 요청은 HTTP 500으로 끝납니다.

`POST /chat/stream`은 단일 Agent의 토큰·도구 진행을 SSE로 보내고, `POST /chat/supervisor/stream`은 계획·Task 상태·Sub-Agent 진행·최종 답변을 SSE로 보냅니다. 두 스트리밍 경로는 `ChatRequest`를 사용하며, 실패하면 `error` 이벤트를 보냅니다. 대화 기록은 프로세스 메모리에만 남습니다.

## 파일과 다음 읽을 곳

| 파일 | 역할 |
| --- | --- |
| [`main.py`](main.py) | FastAPI 시작과 `/health`, `/chat`, 스트리밍 엔드포인트 |
| [`config.py`](config.py) | `OPENAI_MODEL` 설정; 기본 모델은 `gpt-4o` |
| [`schemas/`](schemas/README.md) | 요청과 응답의 데이터 모양 |
| [`agent/`](agent/README.md) | LLM, 도구, 대화 메모리를 연결한 Agent |
| [`streaming/`](streaming/README.md) | LangGraph 이벤트를 SSE 이벤트로 변환 |

프로젝트 루트에서 `uv run --locked --extra backend uvicorn backend.main:app`으로 실행합니다. 실제 모델 호출에는 `OPENAI_API_KEY`가 필요합니다. 외부 호출 없이 HTTP 계약을 확인하려면 [Backend 테스트](../tests/README.md)를 사용하세요.

현재 Next.js 화면은 단일 Agent 경로에 연결되어 있습니다. Supervisor 화면 연결은 후속 단계입니다.
