"""LangSmith 평가자: 응답에서 기대 토픽의 등장 여부를 간단히 확인합니다."""

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
