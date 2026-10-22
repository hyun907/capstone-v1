import assert from "node:assert/strict";
import { test } from "node:test";

import { Chat } from "@ai-sdk/react";

import { BackendChatTransport } from "../lib/transport";
import type { AppMessage } from "../lib/types";

function mockSse(frames: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        const payload = encoder.encode(frames.join(""));
        const split = payload.findIndex((byte) => byte >= 128) + 1;
        controller.enqueue(payload.slice(0, split));
        controller.enqueue(payload.slice(split));
        controller.close();
      },
    }),
    { headers: { "content-type": "text/event-stream" } },
  );
}

function frame(type: string, payload: Record<string, unknown>): string {
  return `event: ${type}\ndata: ${JSON.stringify(payload)}\n\n`;
}

test("AI SDK가 Backend SSE의 도구 상태와 토큰을 메시지로 받는다", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: unknown;
  globalThis.fetch = async (_url, init) => {
    requestBody = JSON.parse(String(init?.body));
    return mockSse([
      frame("tool_call_start", {
        type: "tool_call_start", tool_name: "search_operations_manual", args: { query: "DB" },
      }),
      frame("tool_call_end", {
        type: "tool_call_end", tool_name: "search_operations_manual", result: "합성 결과",
      }),
      frame("token", { type: "token", content: "대응 " }),
      frame("token", { type: "token", content: "절차" }),
      frame("done", { type: "done", thread_id: "thread-test" }),
    ]);
  };

  try {
    const chat = new Chat<AppMessage>({
      id: "thread-test",
      transport: new BackendChatTransport("http://localhost:8000"),
    });
    await chat.sendMessage({ text: "DB 상태" });
    assert.deepEqual(requestBody, { message: "DB 상태", thread_id: "thread-test" });
    assert.equal(chat.messages.length, 2);
    const assistant = chat.messages[1];
    const tools = assistant.parts.filter((part) => part.type === "data-toolProgress");
    assert.equal(tools.length, 1);
    assert.equal(tools[0].data.status, "completed");
    assert.equal(tools[0].data.result, "합성 결과");
    assert.equal(
      assistant.parts.filter((part) => part.type === "text").map((part) => part.text).join(""),
      "대응 절차",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("done 없이 끊어진 응답은 정상 종료로 처리하지 않는다", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => mockSse([
    frame("token", { type: "token", content: "미완성" }),
  ]);

  try {
    const transport = new BackendChatTransport("http://localhost:8000");
    const stream = await transport.sendMessages({
      chatId: "thread-test",
      trigger: "submit-message",
      messageId: undefined,
      messages: [{ id: "user-1", role: "user", parts: [{ type: "text", text: "질문" }] }],
      abortSignal: undefined,
    });
    const reader = stream.getReader();
    await assert.rejects(async () => {
      while (!(await reader.read()).done) { /* consume */ }
    }, /완료 신호 없이/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("API 크레딧 소진 오류의 사용자 안내를 표시한다", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => mockSse([
    frame("error", {
      type: "error",
      code: "API_CREDIT_EXHAUSTED",
      message: "OpenAI API 크레딧이 소진되었습니다.",
    }),
  ]);

  try {
    const transport = new BackendChatTransport("http://localhost:8000");
    const stream = await transport.sendMessages({
      chatId: "thread-test",
      trigger: "submit-message",
      messageId: undefined,
      messages: [{ id: "user-1", role: "user", parts: [{ type: "text", text: "질문" }] }],
      abortSignal: undefined,
    });
    const reader = stream.getReader();
    await assert.rejects(async () => {
      while (!(await reader.read()).done) { /* consume */ }
    }, /OpenAI API 크레딧이 소진되었습니다/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Supervisor SSE를 AI SDK 데이터 파트와 정확한 Task ID로 전달한다", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";
  globalThis.fetch = async (url) => {
    requestedUrl = String(url);
    return mockSse([
      frame("plan_created", { type: "plan_created", plan: "합성 계획" }),
      frame("task_list_created", { type: "task_list_created", tasks: [
        { id: "task_1", description: "조사", agent: "research", status: "pending", result: null },
        { id: "task_2", description: "작성", agent: "writing", status: "pending", result: null },
      ] }),
      frame("task_started", { type: "task_started", task_id: "task_1", agent_name: "research" }),
      frame("sub_agent_tool_call", { type: "sub_agent_tool_call", task_id: "task_1",
        tool_name: "search_operations_manual", args: { query: "DB" }, status: "start", result: null }),
      frame("sub_agent_tool_call", { type: "sub_agent_tool_call", task_id: "task_1",
        tool_name: "search_operations_manual", args: { query: "DB" }, status: "end", result: "합성 결과" }),
      frame("sub_agent_token", { type: "sub_agent_token", task_id: "task_1", content: "조사 " }),
      frame("sub_agent_token", { type: "sub_agent_token", task_id: "task_1", content: "완료" }),
      frame("task_completed", { type: "task_completed", task_id: "task_1", result_preview: "합성 결과" }),
      frame("task_started", { type: "task_started", task_id: "task_2", agent_name: "writing" }),
      frame("sub_agent_token", { type: "sub_agent_token", task_id: "task_2", content: "작성 중" }),
      frame("task_completed", { type: "task_completed", task_id: "task_2", result_preview: "최종 답변" }),
      frame("token", { type: "token", content: "최종 답변" }),
      frame("done", { type: "done", thread_id: "multi-thread" }),
    ]);
  };

  try {
    const chat = new Chat<AppMessage>({
      id: "multi-thread",
      transport: new BackendChatTransport("http://localhost:8000", "multi"),
    });
    await chat.sendMessage({ text: "DB 절차" });
    assert.equal(requestedUrl, "http://localhost:8000/chat/supervisor/stream");
    const parts = chat.messages[1].parts;
    const progress = parts.filter((part) => part.type === "data-supervisorProgress").map((part) => part.data);
    assert.deepEqual(progress.map((event) => event.type), [
      "plan_created", "task_list_created", "task_started", "sub_agent_tool_call",
      "sub_agent_token", "task_completed", "task_started", "sub_agent_token", "task_completed",
    ]);
    assert.deepEqual(
      progress.filter((event) => event.type === "sub_agent_token").map((event) => [event.task_id, event.content]),
      [["task_1", "조사 완료"], ["task_2", "작성 중"]],
    );
    assert.equal(progress.find((event) => event.type === "sub_agent_tool_call")?.status, "end");
    assert.equal(parts.filter((part) => part.type === "text").map((part) => part.text).join(""), "최종 답변");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("잘못된 Supervisor 이벤트는 수락하지 않는다", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => mockSse([
    frame("task_started", { type: "task_started", task_id: "task_1", agent_name: "unknown" }),
  ]);
  try {
    const transport = new BackendChatTransport("http://localhost:8000", "multi");
    const stream = await transport.sendMessages({
      chatId: "multi-thread",
      trigger: "submit-message",
      messageId: undefined,
      messages: [{ id: "user-1", role: "user", parts: [{ type: "text", text: "질문" }] }],
      abortSignal: undefined,
    });
    const reader = stream.getReader();
    await assert.rejects(async () => {
      while (!(await reader.read()).done) { /* consume */ }
    }, /잘못된 스트림 이벤트/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
