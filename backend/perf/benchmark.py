"""동일 질문으로 Supervisor 요청의 지연 시간과 Task 결과를 측정합니다."""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from statistics import mean
from uuid import uuid4

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

from backend.agent.supervisor_graph import build_supervisor_graph  # noqa: E402, I001


BENCHMARK_QUESTIONS = (
    "데이터베이스 다운 시 대응 절차를 알려주세요.",
    "auth-service 시스템 상태와 관련 ticket을 알려주세요.",
    "운영 매뉴얼과 최근 incident를 종합해 장애 대응 가이드를 만들어 주세요.",
    "네트워크 장애 시 첫 단계는?",
    "최근 발생한 critical 등급 incident 목록을 알려주세요.",
)


async def benchmark_request(graph, question: str, *, run_name: str) -> dict:
    """독립 세션에서 한 번 실행하고 최종 Task 상태를 집계합니다."""
    config = {
        "configurable": {"thread_id": str(uuid4())},
        "run_name": run_name,
        "tags": ["a31-cost-latency"],
    }
    start = time.perf_counter()
    try:
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": question}]}, config=config
        )
    except Exception as exc:
        return {
            "question": question,
            "latency_seconds": round(time.perf_counter() - start, 3),
            "num_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "request_error": type(exc).__name__,
        }
    elapsed = time.perf_counter() - start
    tasks = result.get("tasks", [])
    return {
        "question": question,
        "latency_seconds": round(elapsed, 3),
        "num_tasks": len(tasks),
        "completed_tasks": sum(task["status"] == "completed" for task in tasks),
        "failed_tasks": sum(task["status"] == "failed" for task in tasks),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=1, help="질문별 반복 횟수")
    parser.add_argument("--output", type=Path, help="측정 결과 JSON 저장 경로")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats는 1 이상이어야 합니다.")

    graph = await build_supervisor_graph()
    results = []
    for repeat in range(1, args.repeats + 1):
        for index, question in enumerate(BENCHMARK_QUESTIONS, start=1):
            run_name = f"a31-q{index}-run{repeat}"
            print(f"[{run_name}] {question}", flush=True)
            result = await benchmark_request(graph, question, run_name=run_name)
            results.append(result)
            print(
                f"  {result['latency_seconds']:.3f}s | "
                f"{result['completed_tasks']}/{result['num_tasks']} completed | "
                f"{result['failed_tasks']} failed"
                + (
                    f" | request error: {result['request_error']}"
                    if "request_error" in result
                    else ""
                ),
                flush=True,
            )

    summary = {
        "total_requests": len(results),
        "failed_requests": sum("request_error" in result for result in results),
        "average_latency_seconds": round(
            mean(r["latency_seconds"] for r in results), 3
        ),
        "average_tasks_per_request": round(mean(r["num_tasks"] for r in results), 2),
    }
    print("\n=== Summary ===")
    print(f"Total requests: {summary['total_requests']}")
    print(f"Failed requests: {summary['failed_requests']}")
    print(f"Average latency: {summary['average_latency_seconds']:.3f}s")
    print(f"Average tasks per request: {summary['average_tasks_per_request']:.2f}")
    print(f"LangSmith project: {os.getenv('LANGSMITH_PROJECT', 'default')}")
    print("Token usage and cost: inspect the matching LangSmith traces.")

    if args.output:
        args.output.write_text(
            json.dumps(
                {"summary": summary, "results": results}, ensure_ascii=False, indent=2
            )
            + "\n",
            encoding="utf-8",
        )

    if summary["failed_requests"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
