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
| [`eval/`](eval/README.md) | Supervisor 평가 데이터셋과 LangSmith Experiment 실행 |

프로젝트 루트에서 `uv run --locked --extra backend uvicorn backend.main:app`으로 실행합니다. 실제 모델 호출에는 `OPENAI_API_KEY`가 필요합니다. 외부 호출 없이 HTTP 계약을 확인하려면 [Backend 테스트](../tests/README.md)를 사용하세요.

Next.js 화면에서 단일 Agent와 Supervisor 모드를 선택할 수 있습니다.

## Supervisor trace 확인 (O1)

LangGraph와 LangChain의 [LangSmith 추적 안내](https://docs.langchain.com/langsmith/trace-with-langgraph)에 따르면 `LANGSMITH_TRACING=true`와 `LANGSMITH_API_KEY`를 설정하면 별도 계측 코드 없이 그래프 실행을 기록할 수 있습니다. `LANGSMITH_PROJECT`로 trace를 모을 프로젝트를 지정합니다. trace에는 질문, 모델 입출력, 도구 인자와 결과가 포함될 수 있으므로 **합성 데이터만 있는 별도 복사본**에서 확인합니다.

프로젝트 루트에서 추적 중인 파일만 임시 디렉터리로 복사하고, 그곳에 합성 데이터와 추적 전용 환경 파일을 만듭니다. 원본 `mcp-server/data/`는 복사하거나 수정하지 않습니다.

```bash
trace_root=$(mktemp -d)
git archive HEAD | tar -x -C "$trace_root"
cd "$trace_root"
mkdir -p mcp-server/data/runbooks
cat > mcp-server/data/runbooks/db-down.md <<'EOF'
# 합성 데이터베이스 장애 절차

데이터베이스 다운이 의심되면 연결 오류와 헬스 체크를 확인하고, 로그를 살핀 뒤 담당자에게 에스컬레이션합니다. 복구 전에는 영향 범위를 기록합니다.
EOF
cat > mcp-server/data/runbooks/auth-failure.md <<'EOF'
# 합성 인증 장애 절차

로그인 실패 시 인증 서비스 상태와 최근 오류를 확인하고 로그를 살핍니다.
EOF
cat > mcp-server/data/monitoring.json <<'EOF'
{"db-service":{"status":"down","cpu_percent":0,"memory_percent":0,"alerts":["합성 데이터베이스 연결 오류"]},"auth-service":{"status":"healthy","cpu_percent":12,"memory_percent":30,"alerts":[]}}
EOF
```

`backend/.env.trace`를 이 임시 디렉터리에 직접 만들고 아래 **변수 이름**에 본인의 키를 넣습니다. 이 파일은 Git에서 제외되며, Jira 설정은 넣지 않아 mock 검색을 사용합니다. 키가 여러 LangSmith workspace에 연결되어 있다면 `LANGSMITH_WORKSPACE_ID`도 설정합니다. 미국 외 리전이면 계정의 `LANGSMITH_ENDPOINT`를 추가합니다.

```text
OPENAI_API_KEY=<본인의 OpenAI 키>
LANGSMITH_API_KEY=<본인의 LangSmith 키>
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=capstone-observability
```

첫 번째 터미널에서 Backend를 실행하고, 두 번째 터미널에서 과제 질문을 한 번 보냅니다. 기존 셸의 Jira 설정을 제거한 채 실행해야 mock 검색을 유지할 수 있습니다. `uv`의 환경 파일보다 셸 변수가 우선할 수 있으므로 키와 추적 변수도 셸에서 제거한 뒤 전용 파일을 읽습니다.

```bash
env -u OPENAI_API_KEY -u LANGSMITH_API_KEY -u LANGSMITH_TRACING -u LANGSMITH_PROJECT \
  -u JIRA_BASE_URL -u JIRA_EMAIL -u JIRA_API_TOKEN \
  uv run --env-file backend/.env.trace --locked --extra backend \
  uvicorn backend.main:app --host localhost --port 8000
```

```bash
curl -N -X POST http://localhost:8000/chat/supervisor/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"데이터베이스 다운 시 대응 절차와 최근 관련 incident를 종합해 가이드를 만들어 주세요."}'
```

LangSmith의 `capstone-observability` 프로젝트에서 이 요청의 trace ID와 실행 시각을 확인합니다. 현재 그래프의 노드 이름은 `planning → execute_research → execute_writing → finalize`입니다. trace에서 Task 순서, Research·Writing 호출, Tool 이름과 인자, 각 단계의 시간과 토큰을 대조합니다. 비용이나 일부 하위 실행 정보가 표시되지 않으면 값을 추정하지 말고 미확인으로 기록합니다. 캡처에는 합성 데이터와 mock 결과만 보이는지 확인한 후, 임시 디렉터리와 환경 파일을 삭제합니다.

O1 제출 전에는 `results.md`의 모든 값과 캡처가 **같은 trace ID**를 가리키는지 확인합니다. `C1.png`, `C2.png`, `C3.png`, `C4-planning.png`, `C4-toolcall.png`를 결과 파일과 함께 `ai-capstone-observability-{캠퍼스}{X반}-{이름}.zip`에 담고 ZIP 내용 목록을 확인합니다. 개인 제출 ZIP과 캡처는 로컬 다운로드 폴더에만 보관하며 Git에 추가하지 않습니다.

## Error Handling 통합 관찰 (A30)

2026-10-23에 추적 제외된 격리 복사본에 합성 runbook·모니터링 데이터만 넣고 Backend와 Frontend를 실행했습니다. F1의 데이터베이스 다운 대응 절차 질문은 Research와 Writing 두 Task가 모두 `completed`로 끝났고 최종 답변과 `done`을 받았습니다.

E1에서는 Backend를 시작한 뒤 격리 복사본의 MCP 서버 파일 접근을 막았습니다. 원문 질문은 한 번의 실행에서 Writing Task 하나만 계획해 도구 실패를 재현하지 못했습니다. 매뉴얼 검색을 명시한 재시도에서는 Research가 `failed`, Writing이 `completed`로 끝났으며 실패 카드, 실패 안내가 포함된 최종 답변, `done`을 확인했습니다. LangSmith trace에도 `planning → execute_task` 두 번 → `finalize`가 남았습니다. 그래프 전체는 부분 응답으로 정상 종료되므로 root trace의 성공 표시와 개별 Task 실패를 함께 확인해야 합니다. 테스트 후 파일 권한을 복구했습니다.

자동 검증은 프로젝트 루트에서 `uv run --locked --extra backend python -m unittest discover -s tests -q`, `frontend/`에서 `npm test`와 `npm run build`로 실행합니다. 실제 질문에 대한 Task 분해는 모델 출력에 따라 달라질 수 있어 원문 질문만으로 Research 실행이 보장되지는 않습니다. 개인 관찰 캡처와 결과 문서는 공개 저장소에 넣지 않습니다.

## PostgreSQL checkpointer 준비 (A32)

프로젝트 루트의 추적 제외 `.env`에 `POSTGRES_PASSWORD`를 지정합니다. 기본 사용자는 `capstone`, DB는 `capstone_state`, 호스트 포트는 `5432`이며 사용 중인 포트가 있으면 `POSTGRES_PORT`로 바꿀 수 있습니다. Backend의 추적 제외 `backend/.env`에는 같은 접속 정보의 `DATABASE_URL`을 둡니다. 비밀번호나 전체 URL을 Git에 추가하거나 로그에 출력하지 않습니다.

```bash
docker compose up -d postgres
docker compose ps
docker compose exec postgres psql -U capstone -d capstone_state -c '\dt'
uv run --env-file backend/.env --locked --extra backend python -m unittest discover -s tests -p 'test_backend_checkpointer.py' -v
```

`backend.persistence.checkpointer.create_checkpointer()`는 연결을 열고 `setup()`으로 테이블을 준비하며 context 종료 시 연결을 닫습니다. Backend lifespan은 이를 시작 시 한 번 만들고 단일 Agent와 Supervisor에 주입합니다. Backend 실행에도 같은 `.env`를 지정합니다.

```bash
uv run --env-file backend/.env --locked --extra backend uvicorn backend.main:app --port 8000
```

## Cost & Latency 측정 (A31)

최적화 전후 코드의 격리 복사본에 동일한 합성 데이터만 넣고 각각 실행합니다. 실행마다 새 `thread_id`를 사용하며 기본값은 질문 5개를 각 1회 실행합니다. `--repeats N`으로 반복하거나 `--output /tmp/a31-results.json`으로 수치를 저장할 수 있습니다.

```bash
uv run --env-file backend/.env --locked --extra backend python backend/perf/benchmark.py
```

스크립트는 질문별 지연 시간, Task 성공·실패 수와 전체 평균을 출력합니다. 요청 자체가 실패하면 오류 종류만 기록하고 나머지 질문을 계속 실행한 뒤 종료 코드 1을 반환합니다. 토큰과 비용은 같은 실행의 LangSmith trace에서 확인합니다. 서로 다른 계획이나 외부 서비스 상태는 지연 시간 비교에 영향을 주므로 Task 수와 trace를 함께 기록합니다.
