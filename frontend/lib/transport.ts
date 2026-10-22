import type { ChatTransport, UIMessageChunk } from "ai";

import type { AppMessage, StreamEvent, ToolProgress } from "./types";

type SendOptions = Parameters<ChatTransport<AppMessage>["sendMessages"]>[0];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseEvent(frame: string): StreamEvent | null {
  const lines = frame.replace(/\r\n/g, "\n").split("\n");
  const data = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  if (!data) return null;

  const value: unknown = JSON.parse(data);
  if (!isRecord(value)) throw new Error("스트림 이벤트 형식이 올바르지 않습니다.");

  switch (value.type) {
    case "token":
      if (typeof value.content === "string") return { type: "token", content: value.content };
      break;
    case "tool_call_start":
      if (typeof value.tool_name === "string" && isRecord(value.args)) {
        return { type: "tool_call_start", tool_name: value.tool_name, args: value.args };
      }
      break;
    case "tool_call_end":
      if (
        typeof value.tool_name === "string" &&
        (typeof value.result === "string" || value.result === null)
      ) {
        return { type: "tool_call_end", tool_name: value.tool_name, result: value.result };
      }
      break;
    case "done":
      if (typeof value.thread_id === "string") {
        return { type: "done", thread_id: value.thread_id };
      }
      break;
    case "error":
      if (
        (value.code === "MODEL_RATE_LIMIT" || value.code === "STREAM_FAILED") &&
        typeof value.message === "string"
      ) {
        return { type: "error", code: value.code, message: value.message };
      }
      break;
  }
  throw new Error("알 수 없거나 잘못된 스트림 이벤트입니다.");
}

function latestUserText(messages: AppMessage[]): string {
  const user = [...messages].reverse().find((message) => message.role === "user");
  return user?.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("") ?? "";
}

export class BackendChatTransport implements ChatTransport<AppMessage> {
  private readonly backendUrl: string;

  constructor(backendUrl: string) {
    this.backendUrl = backendUrl.replace(/\/$/, "");
  }

  async sendMessages({ chatId, messages, abortSignal }: SendOptions): Promise<ReadableStream<UIMessageChunk>> {
    const message = latestUserText(messages);
    if (!message.trim()) throw new Error("보낼 메시지가 비어 있습니다.");

    let response: Response;
    try {
      response = await fetch(`${this.backendUrl}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, thread_id: chatId }),
        signal: abortSignal,
      });
    } catch (error) {
      if (abortSignal?.aborted) throw error;
      throw new Error("서버에 연결할 수 없습니다. 실행 상태를 확인해 주세요.");
    }
    if (!response.ok) throw new Error(`서버가 요청을 처리하지 못했습니다 (HTTP ${response.status}).`);
    if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream")) {
      throw new Error("서버에서 스트림을 받지 못했습니다.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    return new ReadableStream<UIMessageChunk>({
      async start(controller) {
        const pendingTools: { id: string; value: ToolProgress }[] = [];
        const textId = crypto.randomUUID();
        let textStarted = false;
        let finished = false;
        let buffer = "";
        controller.enqueue({ type: "start" });

        const emit = (event: StreamEvent) => {
          if (finished) throw new Error("완료 이후에 이벤트가 도착했습니다.");
          switch (event.type) {
            case "token":
              if (!textStarted) {
                controller.enqueue({ type: "text-start", id: textId });
                textStarted = true;
              }
              controller.enqueue({ type: "text-delta", id: textId, delta: event.content });
              break;
            case "tool_call_start": {
              const id = crypto.randomUUID();
              const value: ToolProgress = {
                toolName: event.tool_name,
                args: event.args,
                status: "pending",
              };
              pendingTools.push({ id, value });
              controller.enqueue({ type: "data-toolProgress", id, data: value });
              break;
            }
            case "tool_call_end": {
              const pending = [...pendingTools].reverse().find(
                (tool) => tool.value.toolName === event.tool_name && tool.value.status === "pending",
              );
              const id = pending?.id ?? crypto.randomUUID();
              const value: ToolProgress = {
                toolName: event.tool_name,
                args: pending?.value.args ?? {},
                status: "completed",
                result: event.result,
              };
              if (pending) pending.value = value;
              controller.enqueue({ type: "data-toolProgress", id, data: value });
              break;
            }
            case "done":
              if (event.thread_id !== chatId) throw new Error("대화 ID가 일치하지 않습니다.");
              if (textStarted) controller.enqueue({ type: "text-end", id: textId });
              controller.enqueue({ type: "finish" });
              finished = true;
              break;
            case "error":
              throw new Error(event.message);
          }
        };

        try {
          while (true) {
            let chunk: ReadableStreamReadResult<Uint8Array>;
            try {
              chunk = await reader.read();
            } catch (error) {
              if (abortSignal?.aborted) throw error;
              throw new Error("응답 연결이 끊어졌습니다. 다시 시도해 주세요.");
            }
            const { done, value } = chunk;
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let boundary = buffer.search(/\r?\n\r?\n/);
            while (boundary !== -1) {
              const frame = buffer.slice(0, boundary);
              buffer = buffer.slice(boundary).replace(/^\r?\n\r?\n/, "");
              const event = parseEvent(frame);
              if (event) emit(event);
              boundary = buffer.search(/\r?\n\r?\n/);
            }
          }
          if (!finished) throw new Error("응답 연결이 완료 신호 없이 끊어졌습니다.");
          controller.close();
        } catch (error) {
          controller.error(error);
        } finally {
          reader.releaseLock();
        }
      },
      async cancel() {
        await reader.cancel();
      },
    });
  }

  async reconnectToStream(): Promise<null> {
    return null;
  }
}
