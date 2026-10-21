"""조회 전용 MCP 도구와 세션 메모리를 사용하는 단일 Agent."""

from collections.abc import Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import ToolErrorMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from backend.agent.mcp_client import create_mcp_client
from backend.config import AppSettings

READ_ONLY_TOOL_NAMES = frozenset(
    {"get_monitoring_status", "search_operations_manual", "search_jira_tickets"}
)
AGENT_RECURSION_LIMIT = 12

SYSTEM_PROMPT = """당신은 ICT 운영 지원 에이전트입니다. 질문에 필요한 조회 도구만 사용하세요.

T1. 현재 시스템 상태나 활성 알림은 get_monitoring_status로 확인하세요.
T2. 장애 대응 절차나 운영 매뉴얼은 search_operations_manual로 찾으세요.
T3. 기존 incident 기록은 search_jira_tickets로 검색하세요.

조회 결과가 mock인지 실제 응답인지 구분하고, 확인된 사실과 추정을 나눠 설명하세요.
도구가 실패하면 실패 사실을 알리고 확인하지 못한 정보를 지어내지 마세요.
Jira 티켓 생성은 이 채팅에서 사용할 수 없습니다. 생성 요청에는 별도의 사용자 승인 절차가 필요하다고 안내하세요.
"""


async def build_agent(
    *,
    model: BaseChatModel | None = None,
    tools: Sequence[BaseTool] | None = None,
    recursion_limit: int = AGENT_RECURSION_LIMIT,
) -> Runnable:
    """thread_id별 대화를 기억하는 Agent를 만듭니다.

    반환된 Agent 인스턴스를 재사용하고, 호출 설정의
    ``configurable.thread_id``에 동일한 값을 전달해야 문맥이 이어집니다.
    ``recursion_limit``은 한 번의 호출에서 가능한 그래프 단계 수입니다.
    """
    if recursion_limit < 2:
        raise ValueError("recursion_limit은 2 이상이어야 합니다.")

    available_tools = list(tools) if tools is not None else await create_mcp_client().get_tools()
    read_only_tools = [tool for tool in available_tools if tool.name in READ_ONLY_TOOL_NAMES]
    if {tool.name for tool in read_only_tools} != READ_ONLY_TOOL_NAMES:
        raise ValueError("필수 조회 도구 3개를 모두 찾지 못했습니다.")
    if len(read_only_tools) != len(READ_ONLY_TOOL_NAMES):
        raise ValueError("동일한 이름의 조회 도구가 중복되었습니다.")

    chat_model = model if model is not None else ChatOpenAI(
        model=AppSettings().model_name,
        temperature=0,
        max_retries=1,
    )
    agent = create_agent(
        model=chat_model,
        tools=read_only_tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=MemorySaver(),
        middleware=[
            ToolErrorMiddleware(
                on_error=lambda _error, _request: (
                    "조회 도구 실행에 실패했습니다. 잠시 후 다시 시도하거나 연결 설정을 확인하세요."
                )
            )
        ],
    )
    return agent.with_config({"recursion_limit": recursion_limit})
