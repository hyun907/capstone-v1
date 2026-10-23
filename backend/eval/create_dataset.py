"""ICT 운영 Supervisor 평가용 LangSmith 데이터셋을 등록한다."""

import json
import os
from typing import Any

from langsmith import Client
from langsmith.utils import LangSmithAuthError, LangSmithError

DATASET_NAME = "capstone-ict-operations"
DATASET_DESCRIPTION = "ICT 운영 지원 Supervisor의 합성 실습 질문 5건"


def dataset_examples() -> list[dict[str, dict[str, Any]]]:
    """현재 조회 전용 도구와 runbook 범위에 맞는 합성 질문을 반환한다."""
    return [
        {
            "inputs": {"message": "데이터베이스 다운 시 대응 절차를 알려주세요."},
            "outputs": {
                "expected_topics": ["데이터베이스", "진단", "복구", "에스컬레이션"],
                "expected_tools_used": ["search_operations_manual"],
                "should_include_steps": True,
            },
        },
        {
            "inputs": {"message": "auth-service 시스템 상태와 관련 ticket을 알려주세요."},
            "outputs": {
                "expected_topics": ["auth-service", "상태", "티켓"],
                "expected_tools_used": ["get_monitoring_status", "search_jira_tickets"],
                "should_include_steps": False,
            },
        },
        {
            "inputs": {
                "message": "데이터베이스 운영 매뉴얼과 관련 incident를 종합해 장애 대응 가이드를 만들어 주세요."
            },
            "outputs": {
                "expected_topics": ["매뉴얼", "incident", "대응"],
                "expected_tools_used": ["search_operations_manual", "search_jira_tickets"],
                "should_include_steps": True,
            },
        },
        {
            "inputs": {"message": "인증 서비스 로그인 실패 시 먼저 무엇을 확인해야 하나요?"},
            "outputs": {
                "expected_topics": ["인증", "로그인", "확인"],
                "expected_tools_used": ["search_operations_manual"],
                "should_include_steps": True,
            },
        },
        {
            "inputs": {"message": "안녕하세요."},
            "outputs": {
                "expected_topics": ["인사"],
                "expected_tools_used": [],
                "should_include_steps": False,
            },
        },
    ]


def ensure_dataset(client: Client) -> tuple[str, bool]:
    """데이터셋과 예시를 한 번 등록하며 동일 내용의 재실행은 건너뛴다."""
    expected = dataset_examples()
    if client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        existing = list(client.list_examples(dataset_id=dataset.id))
        actual = [{"inputs": item.inputs, "outputs": item.outputs} for item in existing]
        if actual:
            actual_rows = sorted(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in actual)
            expected_rows = sorted(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in expected)
            if actual_rows == expected_rows:
                return str(dataset.id), False
            raise RuntimeError(
                f"'{DATASET_NAME}' 데이터셋에 기존 예시 {len(actual)}건이 있습니다. "
                "내용을 확인한 뒤 다른 데이터셋 이름을 사용하거나 수동으로 정리하세요."
            )
    else:
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description=DATASET_DESCRIPTION,
        )

    client.create_examples(dataset_id=dataset.id, examples=expected)
    return str(dataset.id), True


def main() -> None:
    if not os.getenv("LANGSMITH_API_KEY", "").strip():
        raise SystemExit("LANGSMITH_API_KEY를 설정한 뒤 데이터셋 생성 명령을 다시 실행하세요.")

    try:
        dataset_id, created = ensure_dataset(Client())
    except LangSmithAuthError:
        raise SystemExit("LangSmith 인증에 실패했습니다. LANGSMITH_API_KEY를 확인하세요.") from None
    except LangSmithError:
        raise SystemExit("LangSmith 연결 또는 데이터셋 요청에 실패했습니다. 연결과 권한을 확인하세요.") from None
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None

    action = "등록" if created else "이미 동일한 내용으로 등록됨"
    print(f"Dataset '{DATASET_NAME}': {action} (예시 5건)")
    print(f"https://smith.langchain.com/datasets/{dataset_id}")


if __name__ == "__main__":
    main()
