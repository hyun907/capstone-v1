# 테스트 읽기

테스트는 외부 LLM이나 실제 Jira를 호출하지 않고 현재 동작을 확인하도록 작성되었습니다. 대부분 합성 Agent·모델·도구 또는 HTTP mock을 사용합니다.

| 파일 | 확인하는 내용 |
| --- | --- |
| [`test_backend_main.py`](test_backend_main.py) | `/health`, `/chat`, `thread_id`, 요청 검증과 HTTP 오류 |
| [`test_backend_agent_graph.py`](test_backend_agent_graph.py) | 조회 도구 제한, 대화 메모리, 반복 제한, 도구 오류 |
| [`test_backend_mcp_client.py`](test_backend_mcp_client.py) | MCP subprocess 연결 설정과 도구 탐색 |
| [`test_manual_vector.py`](test_manual_vector.py) | 합성 runbook으로 벡터 인덱스 재사용·갱신 |
| [`test_jira_search_api.py`](test_jira_search_api.py) | Jira 검색 요청·응답과 오류 처리 |
| [`test_jira_create_api.py`](test_jira_create_api.py) | Jira 생성 요청·응답과 승인 조건 |

프로젝트 루트에서 의존성을 설치하고 전체 테스트를 실행합니다.

```bash
uv sync --locked --extra backend
uv run --locked --extra backend python -m unittest discover -s tests -v
```

하나만 살펴보고 싶다면 마지막 명령에 `-p 'test_backend_agent_graph.py'`를 추가하세요. 이 테스트는 실제 OpenAI 응답 품질이나 Next.js 화면을 검증하지 않습니다. 현재 저장소에는 Next.js 화면이 없습니다.
