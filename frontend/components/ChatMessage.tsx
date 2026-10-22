import type { AppMessage } from "@/lib/types";

import { ToolCallView } from "./ToolCallView";

export function ChatMessage({ message }: { message: AppMessage }) {
  const isUser = message.role === "user";

  return (
    <article className={`message ${isUser ? "message-user" : "message-assistant"}`}>
      <div className="message-label">{isUser ? "나" : "ICT 운영 지원 Agent"}</div>
      <div className="message-body">
        {message.parts.map((part, index) => {
          if (part.type === "text") {
            return <p className="message-text" key={`text-${index}`}>{part.text}</p>;
          }
          if (part.type === "data-toolProgress") {
            return <ToolCallView key={part.id ?? `tool-${index}`} tool={part.data} />;
          }
          return null;
        })}
      </div>
    </article>
  );
}
