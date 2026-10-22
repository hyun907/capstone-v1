# Agent 읽기

Agent는 질문에 답할 때 필요한 조회 도구를 LLM이 선택하도록 구성한 코드입니다. 현재 서비스에는 단일 Agent가 연결되어 있습니다. [`supervisor_graph.py`](supervisor_graph.py)에는 Supervisor의 계획과 Research·Writing 실행 흐름이 있지만, HTTP Endpoint와 화면은 아직 연결되지 않았습니다.

## `graph.py`는 무엇을 하나요?

[`graph.py`](graph.py)의 `build_agent()`는 다음을 조립합니다.

1. MCP 서버에서 도구를 가져옵니다. [`mcp_client.py`](mcp_client.py)가 로컬 서버를 stdio subprocess로 연결합니다.
2. 조회용 도구 `get_monitoring_status`, `search_operations_manual`, `search_jira_tickets`만 골라 LLM에 연결합니다. `create_jira_ticket`은 채팅 Agent에 주지 않습니다.
3. `SYSTEM_PROMPT`로 도구 사용 기준과 실습용 mock 데이터의 설명 방식을 알려줍니다.
4. LangChain의 `create_agent()`로 LangGraph 기반 Agent를 만들고 `MemorySaver`를 붙입니다. 코드에서 노드와 연결선을 직접 정의하지는 않습니다.
5. `recursion_limit=12`를 적용해 도구 호출이 계속 반복되는 상황을 제한합니다.

실행 흐름은 `질문 → LLM 판단 → 필요하면 도구 호출 → 도구 결과를 보고 답변`입니다. 도구 호출이 필요 없으면 바로 답할 수도 있습니다. Agent는 답변 문장뿐 아니라 대화 메시지 목록을 반환하고, [`main.py`](../main.py)가 그중 이번 요청에 필요한 내용을 추립니다.

## 대화 메모리

`MemorySaver`는 `configurable.thread_id`를 기준으로 대화를 구분합니다. 같은 서버 프로세스에서 같은 ID를 다시 보내야 이전 대화를 이어 볼 수 있습니다. PostgreSQL 같은 영구 저장은 아직 없습니다.

도구 오류는 현재 Agent에서 별도 안내 문구로 바꾸지 않고 호출자에게 전파합니다. 관련 동작은 [`test_backend_agent_graph.py`](../../tests/test_backend_agent_graph.py)에서 합성 모델과 도구로 검증합니다.

## Supervisor 계획과 실행

`build_supervisor_graph()`는 `planning → start_task → execute_task`를 Task마다 반복하고 `finalize`로 끝납니다. 마지막 사용자 메시지와 이전 대화를 보고 계획과 최대 6개의 Task를 만듭니다. Research Task는 앞에 두고 Writing Task 하나로 끝나야 합니다. 출력은 Pydantic으로 검증하며 잘못된 계획은 실행하지 않습니다.

Research Agent에는 조회 도구 3개만 연결하며 Jira 생성 도구는 제외합니다. Writing Agent는 원래 질문과 앞선 Research 결과를 받아 답변합니다. `start_task`와 `execute_task`가 각각 `in_progress`, `completed`를 기록하므로 이후 SSE 변환에서 두 상태를 별도로 볼 수 있습니다. 작업은 최대 6개이고 그래프 단계 수도 제한합니다. 도구·모델 오류는 호출자에게 전파됩니다.

같은 `thread_id`를 다시 쓰면 메시지 이력은 이어지지만, 매 사용자 턴마다 계획·Task 목록·현재 위치를 새로 작성합니다. 실제 모델 호출 없이 확인하는 테스트는 [`test_backend_supervisor_planning.py`](../../tests/test_backend_supervisor_planning.py)와 [`test_backend_supervisor_execution.py`](../../tests/test_backend_supervisor_execution.py)에 있습니다.
