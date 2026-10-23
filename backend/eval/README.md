# Supervisor 평가

`create_dataset.py`는 LangSmith에 합성 ICT 운영 질문 5건을 등록합니다. 같은 5건이 이미 있으면 건너뛰고, 이름만 같은 다른 데이터셋은 덮어쓰지 않습니다. 현재 지원하는 `db-down`, `auth-failure`, `api-latency` runbook 범위에 맞춰 질문을 골랐습니다.

`run_eval.py`는 HTTP Endpoint를 거치지 않고 Supervisor 그래프를 한 번 준비해 5개 예시를 실행합니다. 예시마다 새 `thread_id`를 사용합니다. `has_expected_topics`는 응답 문자열의 기대 표현을 확인하는 간단한 점수이고, `response_quality`는 구조화된 LLM Judge 점수입니다. 두 점수만으로 Plan·Task·Tool 호출·토큰 효율성을 평가했다고 볼 수는 없습니다.

실제 실행에는 OpenAI와 LangSmith 키가 필요합니다. [Backend의 합성 데이터 trace 절차](../README.md#supervisor-trace-확인-o1)로 만든 임시 복사본에서, 추적 전용 `backend/.env.trace`를 사용합니다. Dataset 생성은 같은 이름의 데이터를 외부 LangSmith에 쓰며, 평가 실행은 모델 호출 비용이 발생합니다. 키와 trace 내용은 공개 저장소에 넣지 않습니다.

```bash
uv run --env-file backend/.env.trace --locked --extra backend python -m backend.eval.create_dataset
uv run --env-file backend/.env.trace --locked --extra backend python -m backend.eval.run_eval
```

첫 명령은 동일 내용이면 다시 실행해도 예시를 늘리지 않습니다. 두 번째 명령은 매번 새 Experiment를 만듭니다. Experiment URL에서 예시별 두 점수와 평균을 확인하세요. 키가 없거나 일부 실행·평가 점수가 빠지면 오류가 납니다.
