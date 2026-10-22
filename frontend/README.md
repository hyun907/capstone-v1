# 스트리밍 채팅 화면

Next.js App Router와 AI SDK `useChat`을 사용해 단일 Agent와 Supervisor의 진행 상황을 표시합니다. [Custom Transport](lib/transport.ts)는 `POST /chat/stream`과 `POST /chat/supervisor/stream`의 SSE를 읽습니다. 화면 상단에서 모드를 바꾸면 각 모드의 대화 ID와 메시지 화면을 따로 사용합니다.

## 로컬 실행

프로젝트 루트에서 Backend를 실행합니다. 실제 모델 호출에는 `OPENAI_API_KEY`가 필요합니다.

```bash
uv run --locked --extra backend uvicorn backend.main:app --port 8000
```

다른 터미널에서 화면을 실행합니다.

```bash
cd frontend
npm ci
npm run dev
```

`http://localhost:3000`에서 질문을 보낼 수 있습니다. Backend 주소를 바꿀 때는 Frontend 실행 전에 `NEXT_PUBLIC_BACKEND_URL`을 설정하세요. 개발용 CORS는 `localhost:3000`과 `127.0.0.1:3000`을 허용합니다.

## 읽는 순서

1. [`app/page.tsx`](app/page.tsx)가 `useChat`을 만들고 화면의 메시지·오류·새 대화 상태를 관리합니다.
2. [`lib/thread.ts`](lib/thread.ts)가 브라우저 `localStorage`에 단일·Supervisor 모드별 대화 ID를 따로 보관합니다. 새로고침하면 ID는 유지되지만 화면의 메시지는 다시 시작합니다.
3. [`lib/transport.ts`](lib/transport.ts)가 Backend SSE를 읽어 AI SDK 메시지 조각으로 바꿉니다. 단일 Agent 도구 상태는 `data-toolProgress`, Supervisor 진행은 `data-supervisorProgress`로 전달합니다.
4. [`components/`](components/)가 메시지, 입력창, 도구 박스, Supervisor의 Plan·Task 카드를 그립니다. 이벤트 필드는 [`lib/types.ts`](lib/types.ts)와 Backend의 [`stream.py`](../backend/schemas/stream.py)에 대응합니다.

Backend의 대화 기록은 `MemorySaver`에 있으므로 Backend를 재시작하면 이전 문맥이 사라집니다. 브라우저의 ID가 남아 있어도 이전 대화 내용을 복원할 수는 없습니다.

## 검증

```bash
cd frontend
npm test
npm run build
npm run test:e2e
```

E2E 테스트는 합성 Agent를 사용하며 실제 OpenAI나 Jira를 호출하지 않습니다. 처음 실행할 때 Chromium이 없으면 `npx playwright install chromium`을 실행하세요. 실제 모델과 실습 데이터를 연결한 화면 동작은 로컬 환경에서 별도로 관찰해야 합니다.
