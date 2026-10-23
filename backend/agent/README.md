# Agent 읽기

Agent는 질문에 답할 때 필요한 조회 도구를 LLM이 선택하도록 구성한 코드입니다. 단일 Agent는 `/chat`과 `/chat/stream`에 연결되어 있습니다. [`supervisor_graph.py`](supervisor_graph.py)의 계획과 Research·Writing 실행 흐름은 `/chat/supervisor/stream`에 연결되어 있고, 화면의 Supervisor 카드에 진행 상황이 표시됩니다.

## `graph.py`는 무엇을 하나요?

[`graph.py`](graph.py)의 `build_agent()`는 다음을 조립합니다.

1. MCP 서버에서 도구를 가져옵니다. [`mcp_client.py`](mcp_client.py)가 로컬 서버를 stdio subprocess로 연결합니다.
2. 조회용 도구 `get_monitoring_status`, `search_operations_manual`, `search_jira_tickets`만 골라 LLM에 연결합니다. `create_jira_ticket`은 채팅 Agent에 주지 않습니다.
3. `SYSTEM_PROMPT`로 도구 사용 기준과 실습용 mock 데이터의 설명 방식을 알려줍니다.
4. LangChain의 `create_agent()`로 LangGraph 기반 Agent를 만들고 주입받은 checkpointer를 붙입니다. 코드에서 노드와 연결선을 직접 정의하지는 않습니다.
5. `recursion_limit=12`를 적용해 도구 호출이 계속 반복되는 상황을 제한합니다.

실행 흐름은 `질문 → LLM 판단 → 필요하면 도구 호출 → 도구 결과를 보고 답변`입니다. 도구 호출이 필요 없으면 바로 답할 수도 있습니다. Agent는 답변 문장뿐 아니라 대화 메시지 목록을 반환하고, [`main.py`](../main.py)가 그중 이번 요청에 필요한 내용을 추립니다.

## 대화 메모리

Backend는 `AsyncPostgresSaver`를 두 그래프에 주입합니다. `configurable.thread_id`가 같으면 재시작하거나 다른 서버 인스턴스로 요청해도 이전 대화를 이어 볼 수 있습니다. 그래프 빌더를 직접 호출하면서 checkpointer를 생략한 경우에만 `MemorySaver`를 사용합니다.

MCP 조회 도구의 timeout은 최대 두 번 재시도한 뒤 `ToolError`로 전파합니다. 다른 실행 오류는 즉시 `ToolError`로 전파하며, 단일 Agent 호출자는 기존처럼 실패를 받습니다. 생성 도구는 중복 쓰기를 막기 위해 재시도 대상에서 제외합니다. 도구 목록을 찾는 시작 단계의 실패는 호출 실패와 구분해 그대로 전파합니다. 관련 동작은 [`test_backend_tool_retry.py`](../../tests/test_backend_tool_retry.py)와 [`test_backend_mcp_client.py`](../../tests/test_backend_mcp_client.py)에서 확인합니다.

## Supervisor 계획과 실행

`build_supervisor_graph()`는 `planning → execute_research → execute_writing → finalize` 순서로 실행합니다. 마지막 사용자 메시지와 이전 대화를 보고 계획과 최대 6개의 Task를 만듭니다. Research Task는 앞에 두고 Writing Task 하나로 끝나야 합니다. 출력은 Pydantic으로 검증하며 형식이 잘못된 계획은 한 번 다시 요청하고, 두 번째도 잘못되면 실행하지 않습니다. 기본 모델은 Planning에 `gpt-4o-mini`, Research·Writing에 `gpt-4o`를 사용합니다. 각각 `OPENAI_PLANNING_MODEL`, `OPENAI_MODEL`로 변경할 수 있습니다.

Research Agent에는 조회 도구 3개만 연결하며 Jira 생성 도구는 제외합니다. 서로 독립적인 Research Task는 최대 5개까지 `asyncio.gather()`로 동시에 실행합니다. 모두 끝난 뒤 Writing Agent가 원래 질문과 성공한 Research 결과, 실패한 작업의 안전한 안내문을 받아 답변합니다. 실패한 Task가 있어도 다른 Task와 Writing을 실행하고, Writing도 실패하면 수집된 자료나 재시도 안내로 빈 답변을 피합니다. 작업은 최대 6개이고 그래프 단계 수도 제한합니다. 계획 수립 실패는 Task가 만들어지기 전이므로 호출자에게 전파됩니다.

같은 `thread_id`를 다시 쓰면 메시지 이력은 이어지지만, 매 사용자 턴마다 계획·Task 목록·현재 위치를 새로 작성합니다. 실제 모델 호출 없이 확인하는 테스트는 [`test_backend_supervisor_planning.py`](../../tests/test_backend_supervisor_planning.py)와 [`test_backend_supervisor_execution.py`](../../tests/test_backend_supervisor_execution.py)에 있습니다.
