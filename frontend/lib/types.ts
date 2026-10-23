import type { UIMessage } from "ai";

export type ChatMode = "single" | "multi";

// backend/schemas/stream.py와 같은 필드 이름을 사용한다.
export type StreamEvent =
  | { type: "token"; content: string }
  | { type: "tool_call_start"; tool_name: string; args: Record<string, unknown> }
  | { type: "tool_call_end"; tool_name: string; result: string | null }
  | { type: "done"; thread_id: string }
  | { type: "error"; code: "API_CREDIT_EXHAUSTED" | "MODEL_RATE_LIMIT" | "STREAM_FAILED" | "STREAM_INTERRUPTED"; message: string; recoverable: boolean }
  | { type: "plan_created"; plan: string }
  | { type: "task_list_created"; tasks: SupervisorTask[] }
  | { type: "task_started"; task_id: string; agent_name: "research" | "writing" }
  | { type: "task_completed"; task_id: string; status: "completed" | "failed"; result_preview: string | null; error_message: string | null }
  | { type: "sub_agent_token"; task_id: string; content: string }
  | { type: "sub_agent_tool_call"; task_id: string; tool_name: string; args: Record<string, unknown>; status: "start" | "end"; result: string | null };

export interface SupervisorTask {
  id: string;
  description: string;
  agent: "research" | "writing";
  status: "pending" | "in_progress" | "completed" | "failed";
  result: string | null;
  error_code?: string;
  error_message?: string;
}

export interface ToolProgress {
  toolName: string;
  args: Record<string, unknown>;
  status: "pending" | "completed";
  result?: string | null;
}

export type SupervisorProgress = Extract<StreamEvent, {
  type: "plan_created" | "task_list_created" | "task_started" | "task_completed" |
    "sub_agent_token" | "sub_agent_tool_call";
}>;

export type AppMessage = UIMessage<unknown, {
  toolProgress: ToolProgress;
  supervisorProgress: SupervisorProgress;
}>;
