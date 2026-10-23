import type { AppMessage } from "@/lib/types";

import { ErrorBanner } from "./ErrorBanner";
import { PlanView } from "./PlanView";
import { TaskListView, type TaskView } from "./TaskListView";
import { ToolCallView } from "./ToolCallView";

export function ChatMessage({ message }: { message: AppMessage }) {
  const isUser = message.role === "user";
  let plan = "";
  let tasks: TaskView[] = [];
  for (const part of message.parts) {
    if (part.type !== "data-supervisorProgress") continue;
    const event = part.data;
    if (event.type === "plan_created") {
      plan = event.plan;
    } else if (event.type === "task_list_created") {
      tasks = event.tasks.map((task) => ({ ...task, token: "", tools: [] }));
    } else if (event.type === "task_started") {
      tasks = tasks.map((task) => task.id === event.task_id ? { ...task, status: "in_progress" } : task);
    } else if (event.type === "task_completed") {
      tasks = tasks.map((task) => task.id === event.task_id ? {
        ...task, status: event.status, result: event.result_preview,
        error_message: event.error_message ?? undefined,
      } : task);
    } else if (event.type === "sub_agent_token") {
      tasks = tasks.map((task) => task.id === event.task_id ? { ...task, token: event.content } : task);
    } else if (event.type === "sub_agent_tool_call") {
      tasks = tasks.map((task) => task.id === event.task_id ? {
        ...task,
        tools: [...task.tools, {
          id: part.id ?? `${event.task_id}:${task.tools.length}`,
          toolName: event.tool_name,
          args: event.args,
          status: event.status,
          result: event.result,
        }],
      } : task);
    }
  }

  return (
    <article className={`message ${isUser ? "message-user" : "message-assistant"}`}>
      <div className="message-label">{isUser ? "나" : "ICT 운영 지원 Agent"}</div>
      <div className="message-body">
        {plan && <PlanView plan={plan} />}
        <TaskListView tasks={tasks} />
        {message.parts.map((part, index) => {
          if (part.type === "text") {
            return <p className={`message-text ${tasks.length ? "final-answer" : ""}`} key={`text-${index}`}>{part.text}</p>;
          }
          if (part.type === "data-toolProgress") {
            return <ToolCallView key={part.id ?? `tool-${index}`} tool={part.data} />;
          }
          if (part.type === "data-errorBanner") {
            return <ErrorBanner key={part.id ?? `error-${index}`}
              message={part.data.message} recoverable={part.data.recoverable} />;
          }
          return null;
        })}
      </div>
    </article>
  );
}
