"""LangSmith에서 Supervisor 평가 Experiment를 실행합니다."""

import asyncio
import os
from collections.abc import Iterable
from typing import Any

from langsmith import aevaluate
from langsmith.utils import LangSmithAuthError, LangSmithError

from backend.eval.create_dataset import DATASET_NAME, dataset_examples
from backend.eval.evaluators import has_expected_topics
from backend.eval.judge import build_response_quality_judge
from backend.eval.target import build_target

EXPERIMENT_PREFIX = "supervisor-v1"
EXPECTED_FEEDBACK_KEYS = {"has_expected_topics", "response_quality"}


def validate_rows(rows: Iterable[dict[str, Any]]) -> int:
    """평가가 빠진 예시를 성공으로 보고하지 않도록 확인합니다."""
    checked = 0
    for row in rows:
        checked += 1
        run = row["run"]
        if run.error or not run.outputs:
            raise RuntimeError(f"예시 {checked}의 Supervisor 실행이 실패했습니다.")
        feedback = row["evaluation_results"]["results"]
        scored_keys = {
            item.key
            for item in feedback
            if isinstance(item.score, (int, float)) and not isinstance(item.score, bool)
        }
        missing = EXPECTED_FEEDBACK_KEYS - scored_keys
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(f"예시 {checked}에 평가 점수가 없습니다: {names}")

    expected_count = len(dataset_examples())
    if checked != expected_count:
        raise RuntimeError(f"평가 예시가 {checked}/{expected_count}건만 완료되었습니다.")
    return checked


async def run_evaluation() -> str:
    """직접 호출 Target과 두 평가자로 데이터셋을 실행합니다."""
    for key in ("LANGSMITH_API_KEY", "OPENAI_API_KEY"):
        if not os.getenv(key, "").strip():
            raise RuntimeError(f"{key}를 설정한 뒤 평가를 실행하세요.")

    target_function = await build_target()
    try:
        results = await aevaluate(
            target_function,
            data=DATASET_NAME,
            evaluators=[has_expected_topics, build_response_quality_judge()],
            experiment_prefix=EXPERIMENT_PREFIX,
            description="ICT 운영 Supervisor 기본 평가",
            max_concurrency=2,
        )
        location = results.url or str(results.experiment_id)
        print(f"Experiment: {location}")
        checked = validate_rows([row async for row in results])
    except LangSmithAuthError:
        raise RuntimeError("LangSmith 인증에 실패했습니다. API 키와 권한을 확인하세요.") from None
    except LangSmithError:
        raise RuntimeError("LangSmith Dataset 또는 Experiment 요청에 실패했습니다.") from None
    print(f"Evaluation completed: {checked} examples, 2 scores each.")
    return location


if __name__ == "__main__":
    asyncio.run(run_evaluation())
