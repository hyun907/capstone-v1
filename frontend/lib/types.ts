import type { UIMessage } from "ai";

// backend/schemas/stream.py와 같은 필드 이름을 사용한다.
export type StreamEvent =
  | { type: "token"; content: string }
  | { type: "tool_call_start"; tool_name: string; args: Record<string, unknown> }
  | { type: "tool_call_end"; tool_name: string; result: string | null }
  | { type: "done"; thread_id: string }
  | { type: "error"; code: "API_CREDIT_EXHAUSTED" | "MODEL_RATE_LIMIT" | "STREAM_FAILED"; message: string };

export interface ToolProgress {
  toolName: string;
  args: Record<string, unknown>;
  status: "pending" | "completed";
  result?: string | null;
}

export type AppMessage = UIMessage<unknown, { toolProgress: ToolProgress }>;
