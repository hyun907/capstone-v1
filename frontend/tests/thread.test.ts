import assert from "node:assert/strict";
import { test } from "node:test";

import { getOrCreateThreadId, startNewThread } from "../lib/thread";

test("단일 Agent와 Supervisor 대화 ID는 별도 저장한다", () => {
  const originalWindow = globalThis.window;
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { localStorage: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    } },
  });
  try {
    const single = getOrCreateThreadId("single");
    const multi = getOrCreateThreadId("multi");
    assert.notEqual(single, multi);
    assert.equal(getOrCreateThreadId("single"), single);
    assert.equal(getOrCreateThreadId("multi"), multi);
    assert.equal(startNewThread("multi"), values.get("capstone:supervisor_thread_id"));
    assert.equal(getOrCreateThreadId("single"), single);
  } finally {
    Object.defineProperty(globalThis, "window", { configurable: true, value: originalWindow });
  }
});
