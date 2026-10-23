"use client";

import { useChat } from "@ai-sdk/react";
import { useEffect, useMemo, useRef, useState } from "react";

import { ChatInput } from "@/components/ChatInput";
import { ChatMessage } from "@/components/ChatMessage";
import { ErrorBanner } from "@/components/ErrorBanner";
import { getOrCreateThreadId, startNewThread } from "@/lib/thread";
import { BackendChatTransport } from "@/lib/transport";
import type { AppMessage, ChatMode } from "@/lib/types";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

function ChatSession({ mode, threadId, onNewThread, onChangeMode }: {
  mode: ChatMode;
  threadId: string;
  onNewThread: () => void;
  onChangeMode: (mode: ChatMode) => void;
}) {
  const transport = useMemo(() => new BackendChatTransport(BACKEND_URL, mode), [mode]);
  const { messages, sendMessage, status, error, stop } = useChat<AppMessage>({
    id: threadId,
    transport,
  });
  const bottomRef = useRef<HTMLDivElement>(null);
  const busy = status === "submitted" || status === "streaming";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  function handleNewThread() {
    stop();
    onNewThread();
  }

  function handleModeChange(nextMode: ChatMode) {
    if (nextMode === mode) return;
    stop();
    onChangeMode(nextMode);
  }

  return (
    <div className="shell">
      <header className="header">
        <div>
          <span className="eyebrow">CAPSTONE · STREAMING</span>
          <h1>ICT 운영 지원 Agent</h1>
          <p>도구 사용과 답변이 진행되는 순서대로 표시됩니다.</p>
          <div className="mode-switch" role="group" aria-label="Agent 모드">
            <button type="button" aria-pressed={mode === "single"} onClick={() => handleModeChange("single")}>Single Agent</button>
            <button type="button" aria-pressed={mode === "multi"} onClick={() => handleModeChange("multi")}>Multi-Agent</button>
          </div>
        </div>
        <div className="header-actions">
          <div className="thread-bar">
            <span className="thread-indicator" />
            <span>대화 ID</span>
            <code title={threadId}>{threadId.slice(0, 8)}</code>
          </div>
          <button className="new-thread" onClick={handleNewThread} type="button">새 대화</button>
        </div>
      </header>

      <main aria-live="polite" className="conversation">
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-mark">↗</div>
            <h2>무엇을 확인할까요?</h2>
            <p>시스템 상태, 운영 매뉴얼, 기존 incident에 관해 질문해 보세요.</p>
          </div>
        ) : (
          messages.map((message) => <ChatMessage key={message.id} message={message} />)
        )}
        {busy && <p className="progress-note">{status === "submitted" ? "응답을 시작하는 중…" : "응답 생성 중…"}</p>}
        {error && <ErrorBanner message={error.message} recoverable={false} />}
        <div ref={bottomRef} />
      </main>

      <footer className="footer">
        <ChatInput disabled={busy} onSend={(text) => void sendMessage({ text })} />
        <p>이 화면의 도구 결과는 실습용 데이터나 Jira 연결 설정에 따라 달라집니다.</p>
      </footer>
    </div>
  );
}

export default function Home() {
  const [mode, setMode] = useState<ChatMode>("single");
  const [threadId, setThreadId] = useState<string | null>(null);

  useEffect(() => {
    setThreadId(getOrCreateThreadId("single"));
  }, []);

  if (!threadId) return <div className="loading-page">대화를 준비하는 중…</div>;
  return <ChatSession
    key={`${mode}:${threadId}`}
    mode={mode}
    threadId={threadId}
    onNewThread={() => setThreadId(startNewThread(mode))}
    onChangeMode={(nextMode) => {
      setMode(nextMode);
      setThreadId(getOrCreateThreadId(nextMode));
    }}
  />;
}
