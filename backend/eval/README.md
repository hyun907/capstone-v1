# Supervisor 평가

`create_dataset.py`는 LangSmith에 합성 ICT 운영 질문 5건을 등록합니다. 같은 5건이 이미 있으면 건너뛰고, 이름만 같은 다른 데이터셋은 덮어쓰지 않습니다. 현재 지원하는 `db-down`, `auth-failure`, `api-latency` runbook 범위에 맞춰 질문을 골랐습니다.

`run_eval.py`는 HTTP Endpoint를 거치지 않고 Supervisor 그래프를 한 번 준비해 5개 예시를 실행합니다. 예시마다 새 `thread_id`를 사용합니다. 응답에는 `has_expected_topics`와 LLM Judge의 `response_quality`를 적용합니다. 계획에는 의도 반영 Judge의 `plan_quality`를, 계획 단계의 Task에는 구조 규칙 `task_structure`와 의미상 분해 Judge의 `task_decomposition_quality`를 적용합니다. Task 평가에는 `agent`와 `description`만 쓰며 실행 후의 `status`와 `result`는 제외합니다. 동일한 Research 설명은 규칙으로 잡고 의미상 중복은 Judge가 판단합니다.

Tool 호출은 Target 실행 중 callback이 실제 호출 이름만 수집하며 인자와 결과는 평가 출력에 복제하지 않습니다. `expected_tool_calls`는 Dataset의 `expected_tools_used`와 실제 이름의 집합을 비교합니다. 둘 다 비면 1점, 한쪽만 비면 0점, 나머지는 `2 × 공통 Tool 수 ÷ (기대 Tool 수 + 실제 Tool 수)`입니다. 누락·추가된 이름을 근거에 남깁니다. 같은 Tool의 반복 호출은 인자에 따라 필요할 수 있어 이 지표가 감점하지 않습니다.

실제 실행에는 OpenAI와 LangSmith 키가 필요합니다. [Backend의 합성 데이터 trace 절차](../README.md#supervisor-trace-확인-o1)로 만든 임시 복사본에서, 추적 전용 `backend/.env.trace`를 사용합니다. Dataset 생성은 같은 이름의 데이터를 외부 LangSmith에 쓰며, 평가 실행은 모델 호출 비용이 발생합니다. 키와 trace 내용은 공개 저장소에 넣지 않습니다.

```bash
uv run --env-file backend/.env.trace --locked --extra backend python -m backend.eval.create_dataset
uv run --env-file backend/.env.trace --locked --extra backend python -m backend.eval.run_eval
```

첫 명령은 동일 내용이면 다시 실행해도 예시를 늘리지 않습니다. 두 번째 명령은 매번 새 `supervisor-v3` Experiment를 만듭니다. Experiment URL에서 예시별 여섯 점수와 평균을 확인하세요. 키가 없거나 일부 실행·평가 점수가 빠지면 오류가 납니다.

## 토큰 효율성 비교

`analyze_tokens.py`는 완료된 두 Experiment의 같은 Dataset 예시 ID를 짝지어 읽는 별도 분석입니다. 새 모델 호출이나 Experiment를 만들지 않습니다. 두 Experiment의 Dataset과 LLM 모델 구성이 같아야 비교합니다. Target trace의 LLM 하위 호출별 input/output/total을 합산하며, 부모 run의 집계값과 Judge 호출은 더하지 않습니다. 각 LLM 호출의 total이 없으면 input과 output 합계로 복원합니다. total을 확인할 수 없거나 부모의 total과 하위 LLM 합계가 다르면 해당 예시는 `측정 불가`로 표시합니다. total은 있지만 input 또는 output 세부값이 빠진 경우 점수는 계산하고 보고서의 해당 값은 `-`로 표시합니다.

같은 질문에 대한 점수는 `min(1, 기준선 total 토큰 / 비교 total 토큰)`입니다. 따라서 인사와 복합 질의를 하나의 절대 한도로 재단하지 않습니다. 점수 1은 기준선 이하의 토큰을 썼다는 뜻일 뿐 응답 품질 개선을 뜻하지 않습니다. 보고서에 두 Experiment의 `response_quality` 점수를 함께 표시하므로 답변 품질도 확인하세요. LangSmith의 cost는 추정치이며 실제 모델 제공사의 청구액과 다를 수 있습니다.

프로젝트 루트에서 기준선·비교 Experiment의 프로젝트 ID를 지정해 실행합니다. 출력은 원문 질문·응답을 포함하지 않는 Markdown입니다. 현재 설치된 LangSmith SDK에서는 `list_runs()`의 폐지 예정 경고가 stderr에 표시될 수 있습니다.

```bash
BASELINE_PROJECT_ID="기준선 프로젝트 UUID"
CANDIDATE_PROJECT_ID="비교 프로젝트 UUID"
uv run --env-file backend/.env --locked --extra backend python -m backend.eval.analyze_tokens \
  --baseline-project-id "$BASELINE_PROJECT_ID" \
  --candidate-project-id "$CANDIDATE_PROJECT_ID" \
  > ~/Downloads/1023/token-efficiency.md
```
