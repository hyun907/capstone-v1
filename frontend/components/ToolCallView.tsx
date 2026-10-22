import type { ToolProgress } from "@/lib/types";

export function ToolCallView({ tool }: { tool: ToolProgress }) {
  return (
    <div className="tool-card">
      <div className="tool-heading">
        <span className={tool.status === "pending" ? "tool-dot pending" : "tool-dot completed"} />
        <span>{tool.status === "pending" ? "도구 실행 중" : "도구 완료"}</span>
        <code>{tool.toolName}</code>
      </div>
      <details>
        <summary>호출 내용 보기</summary>
        <p>인자</p>
        <pre>{JSON.stringify(tool.args, null, 2)}</pre>
        {tool.result && (
          <>
            <p>결과 미리보기</p>
            <pre>{tool.result}</pre>
          </>
        )}
      </details>
    </div>
  );
}
