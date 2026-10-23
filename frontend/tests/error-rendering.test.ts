import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ChatMessage } from "../components/ChatMessage";
import { ErrorBanner } from "../components/ErrorBanner";
import type { AppMessage } from "../lib/types";

test("실패 Task만 빨간 카드가 되고 후속 결과와 부분 답변이 보인다", () => {
  const message: AppMessage = {
    id: "assistant-1", role: "assistant", parts: [
      { type: "data-supervisorProgress", id: "list", data: { type: "task_list_created", tasks: [
        { id: "task_1", description: "매뉴얼 조회", agent: "research", status: "pending", result: null },
        { id: "task_2", description: "답변 작성", agent: "writing", status: "pending", result: null },
      ] } },
      { type: "data-supervisorProgress", id: "failed", data: { type: "task_completed", task_id: "task_1",
        status: "failed", result_preview: null, error_message: "도구 사용 중 문제가 발생했습니다." } },
      { type: "data-supervisorProgress", id: "completed", data: { type: "task_completed", task_id: "task_2",
        status: "completed", result_preview: "합성 결과", error_message: null } },
      { type: "text", text: "확인된 결과만 전달합니다." },
    ],
  };
  const html = renderToStaticMarkup(createElement(ChatMessage, { message }));
  assert.match(html, /task-card task-failed/);
  assert.match(html, /task-card task-completed/);
  assert.match(html, /도구 사용 중 문제가 발생했습니다/);
  assert.match(html, /확인된 결과만 전달합니다/);
});

test("복구 가능 오류는 상태, 복구 불가 오류는 경고 역할로 표시한다", () => {
  const warning = renderToStaticMarkup(createElement(ErrorBanner,
    { message: "일부 결과가 남았습니다.", recoverable: true }));
  const critical = renderToStaticMarkup(createElement(ErrorBanner,
    { message: "다시 시도해 주세요.", recoverable: false }));
  assert.match(warning, /error-banner-warning/);
  assert.match(warning, /role="status"/);
  assert.match(critical, /error-banner-critical/);
  assert.match(critical, /role="alert"/);
});
