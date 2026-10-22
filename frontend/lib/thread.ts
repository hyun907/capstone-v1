const STORAGE_KEY = "capstone:active_thread_id";

export function getOrCreateThreadId(): string {
  try {
    const existing = window.localStorage.getItem(STORAGE_KEY);
    if (existing) return existing;
  } catch {
    // 저장소 접근이 차단된 브라우저에서도 이번 세션의 대화는 사용할 수 있습니다.
  }
  return startNewThread();
}

export function startNewThread(): string {
  const id = crypto.randomUUID();
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // 저장할 수 없으면 새로고침 후 새 ID가 생성됩니다.
  }
  return id;
}
