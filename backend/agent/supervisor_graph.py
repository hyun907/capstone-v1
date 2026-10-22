"""Supervisor의 계획과 작업 분해를 위한 첫 번째 LangGraph 단계."""

from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.config import AppSettings

MAX_TASKS = 6

PLANNING_PROMPT = """당신은 ICT 운영 지원 Supervisor입니다.
가장 최근 사용자 요청을 해결할 짧은 계획과 실행할 작업을 만드세요.
이전 대화는 문맥으로만 참고하세요. 도구를 이미 실행한 것처럼 쓰지 마세요.
작업은 최대 6개이며, 정보 수집이 필요하면 research 작업을 먼저 배치하세요.
마지막 작업은 반드시 writing 하나로 끝내세요. 인사처럼 검색이 불필요하면 writing 작업 하나면 됩니다.
research는 조회만 담당하고 Jira 티켓 생성은 계획하지 마세요.
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
    status: Literal["pending", "in_progress", "completed"]
    result: str | None


class SupervisorState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    plan: NotRequired[str]
    tasks: NotRequired[list[SupervisorTask]]
    current_task_index: NotRequired[int]


async def build_supervisor_graph(
    *,
    planner: Runnable[list[BaseMessage], PlanningDecision] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> Runnable:
    """계획 노드만 가진 그래프를 만들며, 후속 단계에서 실행 노드를 연결합니다."""
    if planner is None:
        model = ChatOpenAI(
            model=AppSettings().model_name,
            temperature=0,
            max_retries=1,
        )
        planner = model.with_structured_output(PlanningDecision)

    async def planning_node(state: SupervisorState) -> dict:
        messages = state["messages"]
        if not messages or not isinstance(messages[-1], HumanMessage):
            raise ValueError("계획을 만들려면 마지막 메시지가 사용자 질문이어야 합니다.")

        decision = PlanningDecision.model_validate(
            await planner.ainvoke([SystemMessage(content=PLANNING_PROMPT), *messages])
        )
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

    workflow = StateGraph(SupervisorState)
    workflow.add_node("planning", planning_node)
    workflow.add_edge(START, "planning")
    workflow.add_edge("planning", END)
    return workflow.compile(checkpointer=checkpointer or MemorySaver())
