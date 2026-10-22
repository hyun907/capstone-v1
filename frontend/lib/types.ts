import type { UIMessage } from "ai";

// backend/schemas/stream.py와 같은 필드 이름을 사용한다.
export type StreamEvent =
  | { type: "token"; content: string }
  | { type: "tool_call_start"; tool_name: string; args: Record<string, unknown> }
  | { type: "tool_call_end"; tool_name: string; result: string | null }
  | { type: "done"; thread_id: string }
  | { type: "error"; code: "API_CREDIT_EXHAUSTED" | "MODEL_RATE_LIMIT" | "STREAM_FAILED"; message: string }
  | { type: "plan_created"; plan: string }
  | { type: "task_list_created"; tasks: SupervisorTask[] }
  | { type: "task_started"; task_id: string; agent_name: "research" | "writing" }
  | { type: "task_completed"; task_id: string; result_preview: string | null }
  | { type: "sub_agent_token"; task_id: string; content: string }
  | { type: "sub_agent_tool_call"; task_id: string; tool_name: string; args: Record<string, unknown>; status: "start" | "end"; result: string | null };

export interface SupervisorTask {
  id: string;
  description: string;
  agent: "research" | "writing";
  status: "pending" | "in_progress" | "completed";
  result: string | null;
}

export interface ToolProgress {
  toolName: string;
  args: Record<string, unknown>;
  status: "pending" | "completed";
  result?: string | null;
}

export type AppMessage = UIMessage<unknown, { toolProgress: ToolProgress }>;
