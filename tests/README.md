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
| [`test_backend_streaming.py`](test_backend_streaming.py) | 단일 Agent SSE와 오류 계약 |
| [`test_backend_supervisor_planning.py`](test_backend_supervisor_planning.py) | Supervisor 계획 검증과 다음 턴 초기화 |
| [`test_backend_supervisor_execution.py`](test_backend_supervisor_execution.py) | Research·Writing 실행 순서와 조회 도구 제한 |
| [`test_backend_supervisor_streaming.py`](test_backend_supervisor_streaming.py) | Supervisor SSE 순서·Task ID·오류 계약 |
| [`test_backend_supervisor_endpoint.py`](test_backend_supervisor_endpoint.py) | Supervisor HTTP SSE와 thread_id 재사용 |
| [`test_backend_eval_dataset.py`](test_backend_eval_dataset.py) | LangSmith Dataset 예시 5건과 중복 생성 방지 |
| [`test_backend_eval_target.py`](test_backend_eval_target.py) | Supervisor 직접 호출 Target과 예시별 thread 분리 |
| [`test_backend_eval_evaluators.py`](test_backend_eval_evaluators.py) | 기대 토픽 평가자의 점수와 누락 처리 |
| [`test_backend_eval_judge.py`](test_backend_eval_judge.py) | LLM Judge의 구조화 점수와 오류 처리 |
| [`test_backend_eval_runner.py`](test_backend_eval_runner.py) | Experiment 실행 설정과 누락 점수 감지 |
| [`test_backend_eval_task_structure.py`](test_backend_eval_task_structure.py) | Task 개수·Writing 순서·인사 과분해·중복 규칙 |
| [`test_backend_eval_plan_task_judge.py`](test_backend_eval_plan_task_judge.py) | 계획과 Task Judge의 입력 분리·점수 계약 |

프로젝트 루트에서 의존성을 설치하고 전체 테스트를 실행합니다.

```bash
uv sync --locked --extra backend
uv run --locked --extra backend python -m unittest discover -s tests -v
```

하나만 살펴보고 싶다면 마지막 명령에 `-p 'test_backend_agent_graph.py'`를 추가하세요. 이 Backend 테스트는 실제 OpenAI 응답 품질을 검증하지 않습니다. Next.js의 합성 검증은 `cd frontend && npm test && npm run test:e2e`로 실행합니다. 실제 모델과 화면에서 관찰한 F1~F3 값은 로컬 제출물에 기록합니다.
