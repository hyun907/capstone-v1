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

## 실습 데이터

별도로 받은 `data-2`의 `monitoring.json`과 `runbooks/`는 로컬의 `mcp-server/data/`에 둡니다. 이 디렉터리는 Git 추적에서 제외되어 있으므로 새 환경에서는 데이터를 다시 배치해야 합니다. 참조 자료의 공유 권한을 확인하기 전에는 원본 파일을 커밋하지 않습니다.
