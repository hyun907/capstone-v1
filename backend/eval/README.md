# Supervisor 평가

`create_dataset.py`는 LangSmith에 합성 ICT 운영 질문 5건을 등록합니다. 같은 5건이 이미 있으면 건너뛰고, 이름만 같은 다른 데이터셋은 덮어쓰지 않습니다. 현재 지원하는 `db-down`, `auth-failure`, `api-latency` runbook 범위에 맞춰 질문을 골랐습니다.

`run_eval.py`는 HTTP Endpoint를 거치지 않고 Supervisor 그래프를 한 번 준비해 5개 예시를 실행합니다. 예시마다 새 `thread_id`를 사용합니다. 응답에는 `has_expected_topics`와 LLM Judge의 `response_quality`를 적용합니다. 계획에는 의도 반영 Judge의 `plan_quality`를, 계획 단계의 Task에는 구조 규칙 `task_structure`와 의미상 분해 Judge의 `task_decomposition_quality`를 적용합니다. Task 평가에는 `agent`와 `description`만 쓰며 실행 후의 `status`와 `result`는 제외합니다. 동일한 Research 설명은 규칙으로 잡고 의미상 중복은 Judge가 판단합니다.

Tool 호출은 Target 실행 중 callback이 실제 호출 이름만 수집하며 인자와 결과는 평가 출력에 복제하지 않습니다. `expected_tool_calls`는 Dataset의 `expected_tools_used`와 실제 이름의 집합을 비교합니다. 둘 다 비면 1점, 한쪽만 비면 0점, 나머지는 `2 × 공통 Tool 수 ÷ (기대 Tool 수 + 실제 Tool 수)`입니다. 누락·추가된 이름을 근거에 남깁니다. 같은 Tool의 반복 호출은 인자에 따라 필요할 수 있어 이 지표가 감점하지 않습니다. 토큰 효율성은 아직 평가하지 않습니다.

실제 실행에는 OpenAI와 LangSmith 키가 필요합니다. [Backend의 합성 데이터 trace 절차](../README.md#supervisor-trace-확인-o1)로 만든 임시 복사본에서, 추적 전용 `backend/.env.trace`를 사용합니다. Dataset 생성은 같은 이름의 데이터를 외부 LangSmith에 쓰며, 평가 실행은 모델 호출 비용이 발생합니다. 키와 trace 내용은 공개 저장소에 넣지 않습니다.

```bash
uv run --env-file backend/.env.trace --locked --extra backend python -m backend.eval.create_dataset
uv run --env-file backend/.env.trace --locked --extra backend python -m backend.eval.run_eval
```

첫 명령은 동일 내용이면 다시 실행해도 예시를 늘리지 않습니다. 두 번째 명령은 매번 새 `supervisor-v3` Experiment를 만듭니다. Experiment URL에서 예시별 여섯 점수와 평균을 확인하세요. 키가 없거나 일부 실행·평가 점수가 빠지면 오류가 납니다.
