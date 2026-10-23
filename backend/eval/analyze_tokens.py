"""동일한 Dataset 예시의 두 LangSmith Experiment에서 토큰 사용을 비교한다."""

import argparse
import math
from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from statistics import mean
from typing import Any

from langsmith import Client
from langsmith.schemas import Run


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    llm_calls: int
    models: frozenset[str]
    estimated_cost_usd: float | None
    reason: str | None = None


@dataclass(frozen=True)
class Comparison:
    example_id: str
    baseline: TokenUsage
    candidate: TokenUsage
    score: float | None
    reason: str | None
    baseline_quality: float | None = None
    candidate_quality: float | None = None


def _token_count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _is_descendant(run: Run, root: Run, by_id: dict[Any, Run]) -> bool:
    parent_id = run.parent_run_id
    visited = {run.id}
    while parent_id is not None and parent_id not in visited:
        if parent_id == root.id:
            return True
        visited.add(parent_id)
        parent = by_id.get(parent_id)
        if parent is None:
            return False
        parent_id = parent.parent_run_id
    return False


def _unavailable(reason: str, llm_calls: int = 0) -> TokenUsage:
    return TokenUsage(None, None, None, llm_calls, frozenset(), None, reason)


def summarize_trace(root: Run, runs: list[Run]) -> TokenUsage:
    """Target trace의 LLM 하위 호출만 한 번씩 합산합니다."""
    if root.error:
        return _unavailable("Target 실행 실패")

    by_id = {run.id: run for run in runs}
    by_id[root.id] = root
    llm_runs = [
        run for run in by_id.values()
        if run.run_type == "llm" and _is_descendant(run, root, by_id)
    ]
    if not llm_runs:
        return _unavailable("LLM 하위 호출 없음")

    input_total: int | None = 0
    output_total: int | None = 0
    total = 0
    models: set[str] = set()
    for run in llm_runs:
        input_count = _token_count(run.prompt_tokens)
        output_count = _token_count(run.completion_tokens)
        recorded_total = _token_count(run.total_tokens)
        if recorded_total == 0:
            recorded_total = None
        if recorded_total is None and input_count is not None and output_count is not None:
            recorded_total = input_count + output_count
        if recorded_total is None or recorded_total == 0:
            return _unavailable("LLM 호출의 토큰 사용량 누락", len(llm_runs))
        if input_count is not None and output_count is not None and input_count + output_count != recorded_total:
            return _unavailable("LLM 호출의 토큰 합계 불일치", len(llm_runs))

        params = (run.extra or {}).get("invocation_params") or {}
        model = params.get("model_name") or params.get("model")
        if not isinstance(model, str) or not model:
            return _unavailable("LLM 모델 식별 불가", len(llm_runs))
        models.add(model)

        total += recorded_total
        input_total = input_total + input_count if input_total is not None and input_count is not None else None
        output_total = output_total + output_count if output_total is not None and output_count is not None else None

    root_total = _token_count(root.total_tokens)
    if root_total is not None and root_total > 0 and root_total != total:
        return _unavailable("Target 합계와 LLM 하위 호출 합계 불일치", len(llm_runs))

    cost = root.total_cost
    estimated_cost = (
        float(cost)
        if isinstance(cost, (int, float, Decimal))
        and not isinstance(cost, bool)
        and math.isfinite(float(cost))
        and cost >= 0
        else None
    )
    return TokenUsage(input_total, output_total, total, len(llm_runs), frozenset(models), estimated_cost)


def compare_usage(example_id: str, baseline: TokenUsage, candidate: TokenUsage) -> Comparison:
    """같은 질문의 기존 토큰 대비 현재 토큰 비율을 0~1로 제한합니다."""
    if baseline.reason or candidate.reason:
        reason = f"기준선: {baseline.reason or '정상'}; 비교: {candidate.reason or '정상'}"
        return Comparison(example_id, baseline, candidate, None, reason)
    if baseline.models != candidate.models:
        return Comparison(example_id, baseline, candidate, None, "LLM 모델 구성이 다름")
    if not baseline.total_tokens or not candidate.total_tokens:
        return Comparison(example_id, baseline, candidate, None, "양쪽의 양수 토큰 합계가 필요함")
    return Comparison(
        example_id, baseline, candidate,
        min(1.0, baseline.total_tokens / candidate.total_tokens), None,
    )


def _project_usage(client: Client, project_id: str) -> tuple[dict[str, TokenUsage], dict[str, float]]:
    runs = list(client.list_runs(project_id=project_id))
    by_trace: dict[Any, list[Run]] = defaultdict(list)
    for run in runs:
        by_trace[run.trace_id].append(run)

    usage_by_example: dict[str, TokenUsage] = {}
    root_to_example: dict[Any, str] = {}
    for root in runs:
        if root.parent_run_id is not None or root.reference_example_id is None:
            continue
        example_id = str(root.reference_example_id)
        if example_id in usage_by_example:
            raise ValueError(f"예시 {example_id}에 Target root가 둘 이상 있습니다.")
        usage_by_example[example_id] = summarize_trace(root, by_trace[root.trace_id])
        root_to_example[root.id] = example_id

    quality_by_example: dict[str, float] = {}
    if root_to_example:
        for feedback in client.list_feedback(
            run_ids=list(root_to_example), feedback_key=["response_quality"]
        ):
            if (
                feedback.key == "response_quality"
                and feedback.run_id in root_to_example
                and isinstance(feedback.score, (int, float))
                and not isinstance(feedback.score, bool)
                and 0 <= feedback.score <= 1
            ):
                quality_by_example[root_to_example[feedback.run_id]] = float(feedback.score)
    return usage_by_example, quality_by_example


def analyze(client: Client, baseline_project_id: str, candidate_project_id: str) -> tuple[str, str, str, list[Comparison]]:
    """같은 Dataset의 예시 ID로 두 Experiment를 짝지어 비교합니다."""
    baseline_project = client.read_project(project_id=baseline_project_id)
    candidate_project = client.read_project(project_id=candidate_project_id)
    dataset_id = baseline_project.reference_dataset_id
    if not dataset_id or dataset_id != candidate_project.reference_dataset_id:
        raise ValueError("두 Experiment의 Dataset이 같아야 합니다.")

    baseline, baseline_quality = _project_usage(client, baseline_project_id)
    candidate, candidate_quality = _project_usage(client, candidate_project_id)
    rows = [
        replace(
            compare_usage(
                example_id,
                baseline.get(example_id, _unavailable("예시 trace 없음")),
                candidate.get(example_id, _unavailable("예시 trace 없음")),
            ),
            baseline_quality=baseline_quality.get(example_id),
            candidate_quality=candidate_quality.get(example_id),
        )
        for example_id in sorted(baseline.keys() | candidate.keys())
    ]
    return baseline_project.name, candidate_project.name, str(dataset_id), rows


def render_markdown(baseline_name: str, candidate_name: str, dataset_id: str, rows: list[Comparison]) -> str:
    """원문 질문과 응답을 노출하지 않는 비교 기록을 만듭니다."""
    lines = [
        "# Token efficiency comparison",
        "",
        f"- Dataset ID: `{dataset_id}`",
        f"- Baseline Experiment: `{baseline_name}`",
        f"- Candidate Experiment: `{candidate_name}`",
        "- 점수: `min(1, 기준선 total / 비교 total)`; 같은 예시 ID와 같은 LLM 모델만 비교",
        "- total은 Target trace 하위 LLM 호출을 한 번씩 합산한 값입니다. Judge 호출과 부모 run 합계는 더하지 않습니다.",
        "- 응답 품질 점수를 함께 보세요. 토큰이 적다는 사실만으로 응답 품질이 높다고 볼 수 없습니다.",
        "- LangSmith cost는 추정치이며 실제 제공사 청구액을 뜻하지 않습니다.",
        "",
        "| 예시 ID | 기준선 input/output/total | 비교 input/output/total | LLM 호출 수 (기준/비교) | 응답 품질 (기준/비교) | 비교 비용 추정 USD | 점수 | 비고 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    scores = []
    for row in rows:
        def fmt_usage(usage: TokenUsage) -> str:
            return "/".join(str(value) if value is not None else "-" for value in (
                usage.input_tokens, usage.output_tokens, usage.total_tokens,
            ))

        cost = f"{row.candidate.estimated_cost_usd:.6f}" if row.candidate.estimated_cost_usd is not None else "-"
        quality = "/".join(
            f"{value:.2f}" if value is not None else "-"
            for value in (row.baseline_quality, row.candidate_quality)
        )
        score = f"{row.score:.3f}" if row.score is not None else "측정 불가"
        if row.score is not None:
            scores.append(row.score)
        notes = [row.reason] if row.reason else []
        if (
            row.baseline_quality is not None
            and row.candidate_quality is not None
            and row.candidate_quality < row.baseline_quality
        ):
            notes.append("응답 품질 점수 하락")
        lines.append(
            f"| `{row.example_id}` | {fmt_usage(row.baseline)} | {fmt_usage(row.candidate)} | "
            f"{row.baseline.llm_calls}/{row.candidate.llm_calls} | {quality} | {cost} | {score} | {'; '.join(notes) or '-'} |"
        )
    average = f"{mean(scores):.3f}" if scores else "측정 불가"
    lines.extend(["", f"측정 가능: {len(scores)}/{len(rows)}건, 평균 점수: {average}", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="같은 Dataset의 LangSmith Experiment 두 개에서 토큰 효율성을 비교합니다.")
    parser.add_argument("--baseline-project-id", required=True)
    parser.add_argument("--candidate-project-id", required=True)
    args = parser.parse_args()
    print(render_markdown(*analyze(Client(), args.baseline_project_id, args.candidate_project_id)))


if __name__ == "__main__":
    main()
