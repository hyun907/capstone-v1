# MCP 서버 읽기

이 폴더는 Agent가 사용할 도구와 실습 데이터를 제공합니다. [`server.py`](server.py)의 `FastMCP`에 **Tool 4개, Resource 1개, Prompt 1개**를 등록했고, 파일을 직접 실행하면 stdio로 통신합니다.

| 종류 | 이름 | 하는 일 |
| --- | --- | --- |
| Tool | `get_monitoring_status` | 로컬 `monitoring.json`에서 시스템 상태 조회 |
| Tool | `search_operations_manual` | 로컬 runbook 키워드 검색 또는 선택적 벡터 검색 |
| Tool | `search_jira_tickets` | Jira 설정이 있으면 Cloud 검색, 없으면 `[mock]` 결과 |
| Tool | `create_jira_ticket` | 설정과 사용자 승인 조건을 확인한 뒤 Jira 티켓 생성; 미설정 시 `[mock]` 결과 |
| Resource | `runbook://incident-response/{incident_type}` | runbook 본문 읽기 |
| Prompt | `incident_analysis_prompt` | 장애 진단 절차 문구 만들기 |

[`backend/agent/graph.py`](../backend/agent/graph.py)의 채팅 Agent에는 위 Tool 중 **조회용 3개만** 연결되어 있습니다. Resource와 Prompt도 현재 `/chat` Agent가 직접 사용하지 않습니다.

## 파일 지도

| 파일 | 역할 |
| --- | --- |
| [`server.py`](server.py) | MCP 항목 등록과 입력 검사, mock 데이터 분기 |
| [`schemas.py`](schemas.py) | 도구 결과의 Pydantic 모델 |
| [`manual_vector.py`](manual_vector.py) | 선택적 로컬 벡터 검색과 메모리 인덱스 |
| [`prepare_vector_model.py`](prepare_vector_model.py) | 벡터 모델 사전 설치 |
| [`jira_search_api.py`](jira_search_api.py), [`jira_create_api.py`](jira_create_api.py) | Jira Cloud HTTP 호출과 응답 변환 |
| [`jira_site.py`](jira_site.py) | Jira 사이트 URL 검사 |

`data/`에는 로컬 실습 데이터를 둡니다. Git에서 제외되므로 새 환경에는 데이터가 없을 수 있습니다. 매뉴얼의 기본 검색은 키워드 방식이고, `mode="vector"`를 지정할 때만 별도 모델이 필요합니다. 준비 명령은 [루트 README](../README.md#운영-매뉴얼-벡터-검색)를 참고하세요.

프로젝트 루트에서 `uv run python mcp-server/server.py`로 실행할 수 있습니다. Inspector 사용법과 Jira 설정은 [루트 README](../README.md#로컬-환경)에 있습니다.
