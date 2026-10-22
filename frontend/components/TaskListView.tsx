import type { SupervisorTask } from "@/lib/types";

export interface TaskTool {
  id: string;
  toolName: string;
  args: Record<string, unknown>;
  status: "start" | "end";
  result: string | null;
}

export interface TaskView extends SupervisorTask {
  token: string;
  tools: TaskTool[];
}

export function TaskListView({ tasks }: { tasks: TaskView[] }) {
  if (tasks.length === 0) return null;

  return (
    <section className="task-list" aria-label="Supervisor 작업 목록">
      <h2>작업 진행</h2>
      <ol>
        {tasks.map((task) => (
          <li key={task.id} className={`task-card task-${task.status}`}>
            <div className="task-heading">
              <span className="task-status">
                {task.status === "pending" ? "대기" : task.status === "in_progress" ? "진행 중" : "완료"}
              </span>
              <span className="task-description">{task.description}</span>
              <code>{task.agent}</code>
            </div>
            {task.tools.map((tool) => (
              <details key={tool.id} className="task-tool">
                <summary>{tool.status === "start" ? "도구 실행 중" : "도구 완료"} · {tool.toolName}</summary>
                <p>인자: {JSON.stringify(tool.args)}</p>
                {tool.result && <p>결과: {tool.result}</p>}
              </details>
            ))}
            {task.status === "in_progress" && task.token && (
              <p className="task-token" aria-label={`${task.id} 진행 내용`}>{task.token.slice(-150)}</p>
            )}
            {task.status === "completed" && task.result && (
              <details className="task-result">
                <summary>결과 보기</summary>
                <p>{task.result}</p>
              </details>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
