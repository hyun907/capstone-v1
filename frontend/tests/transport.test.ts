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
