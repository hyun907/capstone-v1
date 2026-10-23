"""LangSmith 규칙 평가자: 기대 토픽, Task 구조, 실제 Tool 호출을 확인합니다."""

import re

from langsmith.schemas import Example, Run


def _topic_mentioned(topic: str, response: str) -> bool:
    normalized_topic = topic.casefold()
    if normalized_topic in response:
        return True

    # 현재 데이터셋의 두 표현만 보완한다. 일반적인 의미 유사도 판단은 하지 않는다.
    if normalized_topic == "데이터베이스":
        return re.search(r"(?<![a-z0-9])db(?![a-z0-9])", response) is not None
    if normalized_topic == "인사":
        return any(word in response for word in ("안녕", "반갑", "환영"))
    return False


def has_expected_topics(run: Run, example: Example) -> dict[str, str | float]:
    """기대 토픽의 포함 비율을 반환합니다.

    대소문자를 무시한 부분 문자열 비교이며 데이터베이스/DB와 인사말만
    좁게 보완합니다. 나머지 동의어·조사 변화·의미상 동등한 표현은 인식하지
    못하므로 응답 품질의 전체 판단에는 별도 평가자가 필요합니다.
    """
    outputs = example.outputs or {}
    expected = outputs.get("expected_topics")
    if not isinstance(expected, list) or any(
        not isinstance(topic, str) or not topic.strip() for topic in expected
    ):
        return {
            "key": "has_expected_topics",
            "score": 0.0,
            "comment": "Reference expected_topics is missing or invalid.",
        }

    response = (run.outputs or {}).get("response")
    if not isinstance(response, str) or not response.strip():
        return {
            "key": "has_expected_topics",
            "score": 0.0,
            "comment": "Target response is missing or empty.",
        }

    if not expected:
        return {
            "key": "has_expected_topics",
            "score": 1.0,
            "comment": "No expected topics to check.",
        }

    normalized_response = response.casefold()
    missing = [topic for topic in expected if not _topic_mentioned(topic, normalized_response)]
    found = len(expected) - len(missing)
    comment = f"Found {found}/{len(expected)} expected topics."
    if missing:
        comment += f" Missing: {', '.join(missing)}."

    return {
        "key": "has_expected_topics",
        "score": found / len(expected),
        "comment": comment,
    }


def task_structure(run: Run, example: Example) -> dict[str, str | float]:
    """Task 개수·순서·단순 인사·동일 Research 설명을 통과/실패로 평가합니다.

    완료 상태와 실행 결과는 계획의 품질과 무관하므로 읽지 않습니다.
    의미상 중복은 LLM Judge가 따로 평가합니다.
    """
    tasks = (run.outputs or {}).get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return {"key": "task_structure", "score": 0.0, "comment": "Task list is missing or empty."}

    if any(
        not isinstance(task, dict)
        or task.get("agent") not in {"research", "writing"}
        or not isinstance(task.get("description"), str)
        or not task["description"].strip()
        for task in tasks
    ):
        return {"key": "task_structure", "score": 0.0, "comment": "Task role or description is invalid."}

    failures: list[str] = []
    if not 1 <= len(tasks) <= 6:
        failures.append("Task count must be 1-6")

    agents = [task["agent"] for task in tasks]
    if agents[-1] != "writing" or agents.count("writing") != 1:
        failures.append("Exactly one Writing task must be last")

    question = example.inputs.get("message") if example.inputs else None
    if not isinstance(question, str) or not question.strip():
        return {"key": "task_structure", "score": 0.0, "comment": "Reference question is missing."}
    plain_question = re.sub(r"[.!?~。！？\s]+", "", question).casefold()
    if plain_question in {"안녕", "안녕하세요", "반갑습니다", "hi", "hello"} and len(tasks) != 1:
        failures.append("Simple greeting should use one Writing task")

    research_descriptions = [
        re.sub(r"\s+", " ", task["description"].strip()).casefold()
        for task in tasks if task["agent"] == "research"
    ]
    if len(research_descriptions) != len(set(research_descriptions)):
        failures.append("Duplicate Research descriptions")

    return {
        "key": "task_structure",
        "score": 0.0 if failures else 1.0,
        "comment": "; ".join(failures) if failures else "Task structure checks passed.",
    }


def expected_tool_calls(run: Run, example: Example) -> dict[str, str | float]:
    """실제 호출 이름과 Reference의 집합을 F1 점수로 비교합니다.

    같은 Tool을 여러 번 호출한 경우 인자별 필요성은 이 지표로 판단하지 않습니다.
    """
    expected = (example.outputs or {}).get("expected_tools_used")
    actual = (run.outputs or {}).get("tools_used")
    if not isinstance(expected, list) or any(
        not isinstance(name, str) or not name.strip() for name in expected
    ):
        return {"key": "expected_tool_calls", "score": 0.0, "comment": "Reference Tool list is missing or invalid."}
    if not isinstance(actual, list) or any(
        not isinstance(name, str) or not name.strip() for name in actual
    ):
        return {"key": "expected_tool_calls", "score": 0.0, "comment": "Recorded Tool list is missing or invalid."}

    expected_names = set(expected)
    actual_names = set(actual)
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    if not expected_names and not actual_names:
        score = 1.0
    elif not expected_names or not actual_names:
        score = 0.0
    else:
        score = 2 * len(expected_names & actual_names) / (len(expected_names) + len(actual_names))

    return {
        "key": "expected_tool_calls",
        "score": score,
        "comment": (
            f"Expected: {sorted(expected_names)}; used: {sorted(actual_names)}; "
            f"missing: {missing}; extra: {extra}."
        ),
    }
