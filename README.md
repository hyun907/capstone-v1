# AI Agent 개인 실습

AI Agent 서비스를 단계별로 직접 구현하고 검증하는 개인 실습 저장소입니다. 현재 MCP 서버에서 Tool 4개, Resource 1개, Prompt 1개를 제공합니다.

## 진행 범위

- MCP 도구와 FastAPI 연동
- SSE 스트리밍과 Supervisor 기반 에이전트 흐름
- 평가, 오류 처리, 성능 측정, 세션 저장
- 필요하면 구조 개선과 리팩터링

구현 단계와 실제 완료 여부는 이후 이슈와 PR에서 기록합니다.

## 작업 방식

- [코드·Git 컨벤션](docs/CONVENTIONS.md)을 따릅니다.
- [에이전트 작업 지침](AGENTS.md)을 작업 전에 확인합니다.
- 기능은 작은 단위로 구현하고, PR에 검증 명령과 결과를 남깁니다.
- 별도로 제공된 참조 자료는 학습·비교에만 사용합니다. 참조 구현이나 파일을 이 저장소에 복사해 공개하지 않습니다.

## 로컬 환경

Python 3.11과 `uv`를 사용합니다. 프로젝트 루트에서 `uv sync --locked`로 MCP 서버 의존성을 설치합니다. API 키와 연결 정보는 `.env` 같은 추적 제외 파일에 보관합니다.

서버는 stdio로 실행합니다. MCP Inspector에서는 아래 두 번째 명령을 사용하고, 터미널에 표시되는 로컬 주소에서 Connect를 누릅니다.

```bash
uv run python mcp-server/server.py
npx @modelcontextprotocol/inspector@v1-latest uv run python mcp-server/server.py
```

Inspector에서 `get_monitoring_status`, `search_operations_manual`, `search_jira_tickets`, `create_jira_ticket` Tool과 `runbook://incident-response/{incident_type}` Resource Template, `incident_analysis_prompt` Prompt를 확인할 수 있습니다. Jira 검색은 `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`이 모두 설정되면 Jira Cloud를 조회하고, 누락 시 mock 결과를 반환합니다. Jira 생성은 같은 설정이 모두 있고 사용자가 승인한 뒤 `user_confirmed=true`로 호출하면 실제 티켓을 생성합니다. 설정이 부족하면 `[mock]` 결과를 반환합니다.

### 운영 매뉴얼 벡터 검색

`search_operations_manual`의 기본 `mode="keyword"`는 기존 키워드 mock 검색입니다. `mode="vector"`를 명시하면 로컬 다국어 임베딩 모델로 의미가 가까운 runbook 문장을 찾습니다. `query`, `top_k`, `ManualSnippet` 결과 계약은 그대로이며, 벡터 점수는 코사인 유사도라 키워드 등장 횟수 점수와 척도가 다릅니다. 현재는 작은 runbook 집합을 메모리에 인덱싱하고 파일 내용이 바뀌면 다음 검색에서 다시 인덱싱합니다.

벡터 검색을 사용할 때만 선택 의존성과 [다국어 E5-small](https://huggingface.co/intfloat/multilingual-e5-small) 모델을 설치합니다. FastEmbed 사용자 지정 모델 등록으로 [ONNX O4 파일](https://huggingface.co/intfloat/multilingual-e5-small/tree/main/onnx)을 사용하며 모델 파일은 약 235MB입니다. 아래 사전 설치 명령은 공개 모델 파일만 내려받고 runbook을 읽지 않습니다. 모델 캐시는 Git에서 제외된 프로젝트 루트의 `.model-cache/`에 두며, 원본 runbook이 있는 `mcp-server/data/`에는 쓰지 않습니다.

```bash
uv sync --extra vector
export FASTEMBED_CACHE_PATH="$PWD/.model-cache"
uv run --extra vector python mcp-server/prepare_vector_model.py
```

벡터 모드를 사용할 서버와 Inspector도 선택 의존성을 포함해 실행합니다.

```bash
uv run --extra vector python mcp-server/server.py
npx @modelcontextprotocol/inspector@v1-latest uv run --extra vector python mcp-server/server.py
```

서버는 같은 `FASTEMBED_CACHE_PATH`에서 `local_files_only=True`로 모델을 열어 검색할 때 네트워크를 사용하지 않습니다. 선택 의존성이 없거나 모델 캐시가 비어 있으면 벡터 검색은 설치 안내 오류를 반환합니다. runbook 디렉터리가 없으면 빈 목록을 반환합니다. 관련 없는 질의는 실습용 유사도 기준(`0.83`) 미만일 때 빈 목록을 반환하므로, 새 문서를 추가할 때 기준값을 다시 검증해야 합니다.

### Backend 채팅 계약 준비

FastAPI와 Agent 연결에 사용할 Python 의존성은 `backend` 선택 그룹에 있습니다. 현재는 채팅 요청·응답 스키마와 설정을 확인할 수 있으며, HTTP 채팅 엔드포인트는 다음 단계에서 추가합니다.

```bash
uv sync --locked --extra backend
uv run --locked --extra backend python -c "from backend.config import AppSettings; from backend.schemas.chat import ChatRequest, ChatResponse; print(AppSettings().model_name)"
```

모델 이름은 `OPENAI_MODEL` 환경변수로 변경할 수 있고 기본값은 `gpt-4o`입니다. 이후 Agent 연결에 필요한 `OPENAI_API_KEY`도 프로세스 환경변수로 전달합니다. 로컬 `backend/.env`를 쓰는 경우 `uv run --env-file backend/.env --extra backend ...`로 불러올 수 있으며, 이 파일은 Git 추적에서 제외됩니다. `AppSettings.openai_api_key_configured`는 키를 출력·저장하지 않고 비어 있지 않은지만 확인합니다.

### Backend MCP 도구 연결

Backend에서는 `backend.agent.mcp_client.create_mcp_client()`로 로컬 MCP 서버 연결을 구성합니다. `await client.get_tools()`를 호출하면 현재 Python 실행 파일과 서버 파일의 절대 경로로 stdio subprocess를 열고 LangChain Tool 4개를 불러옵니다. 반환된 Tool은 `await tool.ainvoke({...})`로 호출합니다.

이 어댑터는 `get_tools()`가 탐색할 때 세션을 열었다가 닫고, 반환된 Tool을 호출할 때도 새 세션과 subprocess를 엽니다. 따라서 Tool 목록을 가져온 뒤 서버가 계속 실행 중이라고 가정하면 안 됩니다. Jira 연결 설정과 벡터 모델 캐시 경로를 사용할 경우 `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `FASTEMBED_CACHE_PATH`만 서버 subprocess에 전달합니다. 값은 로그에 출력하지 않습니다.

```bash
uv sync --locked --extra backend
uv run --locked --extra backend python -m unittest discover -s tests -p 'test_backend_mcp_client.py' -v
```

MCP 클라이언트는 도구 연결만 제공하며 HTTP 채팅 엔드포인트는 아직 없습니다.

### 단일 Agent와 세션 메모리

`backend.agent.graph.build_agent()`는 기존 MCP 클라이언트가 찾은 Tool 4개 중 조회용 3개(`get_monitoring_status`, `search_operations_manual`, `search_jira_tickets`)만 Agent에 연결합니다. `create_jira_ticket`은 채팅 요청 스키마에 신뢰할 수 있는 생성 승인값이 없어 제외했습니다. Agent에는 시스템 상태·매뉴얼·Jira 이력 질문에 맞는 조회 도구를 선택하고 mock 응답을 구분하도록 지시합니다. 도구 실행 실패는 내부 오류 내용을 빼고 안내합니다.

모델은 기본 `gpt-4o`이며 `OPENAI_MODEL`로 변경할 수 있습니다. `MemorySaver`는 같은 Agent 인스턴스와 `configurable.thread_id`를 재사용할 때 대화를 이어 줍니다. 메모리는 프로세스 RAM에만 있고 재시작하면 사라집니다. Agent 실행에는 기본 `recursion_limit=12`를 적용해 도구 호출 반복을 제한합니다. 이번 단계에서는 원본 runbook이나 모니터링 데이터를 외부 모델로 보내지 않았습니다. 실제 실행 전에 데이터 사용 권한을 확인해야 합니다.

외부 API와 원본 데이터를 쓰지 않는 합성 테스트:

```bash
uv run --locked --extra backend python -m unittest discover -s tests -p 'test_backend_agent_graph.py' -v
```

HTTP `/chat` 연결은 다음 단계에서 추가합니다.

## 실습 데이터

별도로 받은 `data-2`의 `monitoring.json`과 `runbooks/`는 로컬의 `mcp-server/data/`에 둡니다. 이 디렉터리는 Git 추적에서 제외되어 있으므로 새 환경에서는 데이터를 다시 배치해야 합니다. 참조 자료의 공유 권한을 확인하기 전에는 원본 파일을 커밋하지 않습니다.
