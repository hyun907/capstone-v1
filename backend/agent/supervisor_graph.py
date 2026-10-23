"""Supervisor가 계획을 만들고 조회·작성 작업을 순서대로 실행하는 그래프."""

from collections.abc import Sequence
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from backend.agent.graph import READ_ONLY_TOOL_NAMES
from backend.agent.mcp_client import get_mcp_tools
from backend.config import AppSettings
from backend.error_handling.classification import classify_exception
from backend.schemas.error import ErrorLayer, ToolError

MAX_TASKS = 6
MAX_PLANNING_ATTEMPTS = 2
SUPERVISOR_RECURSION_LIMIT = 2 * MAX_TASKS + 6

PLANNING_PROMPT = """당신은 ICT 운영 지원 Supervisor입니다.
가장 최근 사용자 요청을 해결할 짧은 계획과 실행할 작업을 만드세요.
이전 대화는 문맥으로만 참고하세요. 도구를 이미 실행한 것처럼 쓰지 마세요.
작업은 최대 6개이며, 정보 수집이 필요하면 research 작업을 먼저 배치하세요.
마지막 작업은 반드시 writing 하나로 끝내세요. 인사처럼 검색이 불필요하면 writing 작업 하나면 됩니다.
research는 조회만 담당하고 Jira 티켓 생성은 계획하지 마세요.
"""

RESEARCH_PROMPT = """당신은 ICT 운영 지원 Research Agent입니다.
필요한 사실은 연결된 조회 도구로 확인하고, 수집한 결과와 출처를 간결하게 정리하세요.
도구 결과의 mock 여부를 구분하고, 없는 정보를 지어내지 마세요.
Jira 티켓 생성은 수행하지 마세요.
"""

WRITING_PROMPT = """당신은 ICT 운영 지원 Writing Agent입니다.
사용자의 원래 요청과 제공된 Research 결과를 바탕으로 답변하세요.
확인된 사실과 추정을 구분하고, 조회 결과가 없으면 그 한계를 밝혀 주세요.
Research 결과가 실습용 또는 mock 데이터라면 첫 문장에 그 기준을 명시하세요.
"""


class TaskDraft(BaseModel):
    description: str = Field(description="Sub-Agent에게 맡길 구체적인 작업")
    agent: Literal["research", "writing"]

    @field_validator("description")
    @classmethod
    def reject_blank_description(cls, value: str) -> str:
        description = value.strip()
        if not description:
            raise ValueError("작업 설명은 비어 있을 수 없습니다.")
        return description


class PlanningDecision(BaseModel):
    plan: str = Field(description="사용자에게 보여줄 짧은 전체 계획")
    tasks: list[TaskDraft] = Field(min_length=1, max_length=MAX_TASKS)

    @field_validator("plan")
    @classmethod
    def reject_blank_plan(cls, value: str) -> str:
        plan = value.strip()
        if not plan:
            raise ValueError("계획은 비어 있을 수 없습니다.")
        return plan

    @model_validator(mode="after")
    def require_final_writing_task(self) -> "PlanningDecision":
        writing_positions = [
            index for index, task in enumerate(self.tasks) if task.agent == "writing"
        ]
        if writing_positions != [len(self.tasks) - 1]:
            raise ValueError("writing 작업은 마지막에 하나만 있어야 합니다.")
        return self


class SupervisorTask(TypedDict):
    id: str
    description: str
    agent: Literal["research", "writing"]
    status: Literal["pending", "in_progress", "completed", "failed"]
    result: str | None
    error_code: NotRequired[str]
    error_message: NotRequired[str]


class SupervisorState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    plan: NotRequired[str]
    tasks: NotRequired[list[SupervisorTask]]
    current_task_index: NotRequired[int]


async def build_supervisor_graph(
    *,
    planner: Runnable[list[BaseMessage], PlanningDecision] | None = None,
    research_agent: Runnable | None = None,
    writing_agent: Runnable | None = None,
    model: BaseChatModel | None = None,
    tools: Sequence[BaseTool] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> Runnable:
    """조회 전용 Research와 LLM Writing을 포함한 Supervisor를 만듭니다."""
    if planner is None or research_agent is None or writing_agent is None:
        model = model if model is not None else ChatOpenAI(
            model=AppSettings().model_name,
            temperature=0,
            max_retries=1,
        )

    if planner is None:
        planner = model.with_structured_output(PlanningDecision)

    if research_agent is None:
        available_tools = list(tools) if tools is not None else await get_mcp_tools()
        read_only_tools = [tool for tool in available_tools if tool.name in READ_ONLY_TOOL_NAMES]
        if {tool.name for tool in read_only_tools} != READ_ONLY_TOOL_NAMES:
            raise ValueError("필수 조회 도구 3개를 모두 찾지 못했습니다.")
        if len(read_only_tools) != len(READ_ONLY_TOOL_NAMES):
            raise ValueError("동일한 이름의 조회 도구가 중복되었습니다.")
        research_agent = create_agent(
            model=model,
            tools=read_only_tools,
            system_prompt=RESEARCH_PROMPT,
        )

    if writing_agent is None:
        writing_agent = create_agent(
            model=model,
            tools=[],
            system_prompt=WRITING_PROMPT,
        )

    async def planning_node(state: SupervisorState) -> dict:
        messages = state["messages"]
        if not messages or not isinstance(messages[-1], HumanMessage):
            raise ValueError("계획을 만들려면 마지막 메시지가 사용자 질문이어야 합니다.")

        planning_messages = [SystemMessage(content=PLANNING_PROMPT), *messages]
        for attempt in range(MAX_PLANNING_ATTEMPTS):
            try:
                decision = PlanningDecision.model_validate(
                    await planner.ainvoke(planning_messages)
                )
                break
            except ValidationError:
                if attempt == MAX_PLANNING_ATTEMPTS - 1:
                    raise
                planning_messages = [
                    *planning_messages,
                    HumanMessage(
                        content=(
                            "앞선 계획이 형식 규칙을 위반했습니다. "
                            "최대 6개 작업으로 다시 작성하고, research 작업을 먼저 배치한 뒤 "
                            "마지막에 writing 작업을 정확히 하나만 두세요."
                        )
                    ),
                ]
        tasks: list[SupervisorTask] = [
            {
                "id": f"task_{index}",
                "description": task.description,
                "agent": task.agent,
                "status": "pending",
                "result": None,
            }
            for index, task in enumerate(decision.tasks, start=1)
        ]
        return {"plan": decision.plan, "tasks": tasks, "current_task_index": 0}

    async def start_task_node(state: SupervisorState) -> dict:
        index = state["current_task_index"]
        tasks = list(state["tasks"])
        if not 0 <= index < len(tasks) or tasks[index]["status"] != "pending":
            raise ValueError("시작할 수 있는 대기 작업이 없습니다.")
        tasks[index] = {**tasks[index], "status": "in_progress"}
        return {"tasks": tasks}

    async def execute_task_node(state: SupervisorState) -> dict:
        index = state["current_task_index"]
        tasks = list(state["tasks"])
        if not 0 <= index < len(tasks) or tasks[index]["status"] != "in_progress":
            raise ValueError("실행 중인 작업이 없습니다.")

        task = tasks[index]
        latest_user = next(
            message for message in reversed(state["messages"])
            if isinstance(message, HumanMessage)
        )
        if task["agent"] == "research":
            agent = research_agent
            request = (
                f"원래 사용자 요청:\n{latest_user.content}\n\n"
                f"현재 Research 작업:\n{task['description']}"
            )
        else:
            agent = writing_agent
            findings = "\n\n".join(
                f"- {previous['description']}\n  결과: {previous['result']}"
                for previous in tasks[:index]
                if previous["agent"] == "research" and previous["status"] == "completed"
            )
            failures = "\n".join(
                f"- {previous['description']}: {previous['error_message']}"
                for previous in tasks[:index]
                if previous["agent"] == "research" and previous["status"] == "failed"
            )
            request = (
                f"원래 사용자 요청:\n{latest_user.content}\n\n"
                f"Research 결과:\n{findings or '확인된 조회 결과 없음'}\n\n"
                f"실패한 Research 작업:\n{failures or '없음'}\n\n"
                "확인되지 않은 정보는 추정하지 말고, 실패한 정보 수집은 사용자에게 알려 주세요.\n\n"
                f"현재 Writing 작업:\n{task['description']}"
            )

        try:
            result = await agent.ainvoke(
                {"messages": [*state["messages"], HumanMessage(content=request)]}
            )
            response = result["messages"][-1]
            if not isinstance(response, AIMessage) or not isinstance(response.content, str):
                raise ValueError("Sub-Agent가 텍스트 답변을 반환하지 않았습니다.")
            result_text = response.content.strip()
            if not result_text:
                raise ValueError("Sub-Agent가 빈 답변을 반환했습니다.")
            tasks[index] = {**task, "status": "completed", "result": result_text}
        except ToolError as exc:
            tasks[index] = {
                **task,
                "status": "failed",
                "result": None,
                "error_code": exc.error.code,
                "error_message": exc.error.user_message or "도구 사용 중 문제가 발생했습니다.",
            }
        except Exception as exc:
            error = classify_exception(
                exc, layer=ErrorLayer.ORCHESTRATION,
                operation="response" if task["agent"] == "writing" else None,
            )
            tasks[index] = {
                **task,
                "status": "failed",
                "result": None,
                "error_code": error.code,
                "error_message": error.user_message or "작업을 처리하지 못했습니다.",
            }
        return {"tasks": tasks, "current_task_index": index + 1}

    def route_after_execution(state: SupervisorState) -> Literal["start_task", "finalize"]:
        index = state["current_task_index"]
        if index < len(state["tasks"]):
            return "start_task"
        return "finalize"

    async def finalize_node(state: SupervisorState) -> dict:
        tasks = state["tasks"]
        if not tasks or tasks[-1]["agent"] != "writing":
            raise ValueError("Writing 작업이 없어 답변을 확정할 수 없습니다.")

        writing = tasks[-1]
        failed_count = sum(task["status"] == "failed" for task in tasks)
        if writing["status"] == "completed" and writing["result"]:
            final_response = writing["result"]
            if failed_count:
                final_response += "\n\n일부 정보 수집에 실패하여 확인된 결과만 반영했습니다."
        else:
            partial_results = [
                f"- {task['description']}: {task['result']}"
                for task in tasks[:-1]
                if task["status"] == "completed" and task["result"]
            ]
            if partial_results:
                final_response = (
                    "응답 생성에 문제가 있어 확인된 자료를 그대로 전달합니다. "
                    + ("일부 정보 수집에도 실패했습니다. " if failed_count > 1 else "")
                    + "\n\n"
                    + "\n".join(partial_results)
                )
            else:
                final_response = (
                    "요청을 처리하는 중 문제가 발생해 정보를 확인하지 못했습니다. "
                    "잠시 후 다시 시도해 주세요."
                )
        return {"messages": [AIMessage(content=final_response)]}

    workflow = StateGraph(SupervisorState)
    workflow.add_node("planning", planning_node)
    workflow.add_node("start_task", start_task_node)
    workflow.add_node("execute_task", execute_task_node)
    workflow.add_node("finalize", finalize_node)
    workflow.add_edge(START, "planning")
    workflow.add_edge("planning", "start_task")
    workflow.add_edge("start_task", "execute_task")
    workflow.add_conditional_edges("execute_task", route_after_execution)
    workflow.add_edge("finalize", END)
    return workflow.compile(checkpointer=checkpointer or MemorySaver()).with_config(
        {"recursion_limit": SUPERVISOR_RECURSION_LIMIT}
    )
