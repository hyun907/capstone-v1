import { expect, test } from "@playwright/test";

test("도구 상태, 토큰, 대화 ID와 새 대화를 화면에 반영한다", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "ICT 운영 지원 Agent" })).toBeVisible();
  const firstId = await page.locator(".thread-bar code").textContent();
  const header = await page.locator(".header").boundingBox();
  const thread = await page.locator(".thread-bar").boundingBox();
  expect(header).not.toBeNull();
  expect(thread).not.toBeNull();
  expect(thread!.x).toBeGreaterThan(header!.x + header!.width / 2);
  expect(thread!.y).toBeLessThan(header!.y + header!.height);

  await page.getByLabel("메시지").fill("데이터베이스 다운 절차");
  await page.getByRole("button", { name: "전송" }).click();
  await expect(page.getByText("도구 실행 중")).toBeVisible();
  await expect(page.getByText("도구 완료")).toBeVisible();
  await expect(page.getByText(/합성 응답. 이전 질문: 없음/)).toBeVisible();
  await expect(page.getByText(/현재 질문: 데이터베이스 다운 절차/)).not.toBeVisible();
  await expect(page.getByText(/현재 질문: 데이터베이스 다운 절차/)).toBeVisible();
  await expect(page.getByLabel("메시지")).toBeEnabled();

  await page.getByLabel("메시지").fill("첫 단계는?");
  await page.getByRole("button", { name: "전송" }).click();
  await expect(page.getByText(/이전 질문: 데이터베이스 다운 절차/)).toBeVisible();
  await expect(page.locator(".thread-bar code")).toHaveText(firstId ?? "");

  await page.reload();
  await expect(page.locator(".thread-bar code")).toHaveText(firstId ?? "");
  await expect(page.getByText("무엇을 확인할까요?")).toBeVisible();

  await page.getByRole("button", { name: "새 대화" }).click();
  await expect(page.locator(".thread-bar code")).not.toHaveText(firstId ?? "");
  await page.getByLabel("메시지").fill("첫 단계는?");
  await page.getByRole("button", { name: "전송" }).click();
  await expect(page.getByText(/이전 질문: 없음/)).toBeVisible();
});

test("스트림이 중간에 실패하면 화면에 오류를 표시한다", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("메시지").fill("오류 확인");
  await page.getByRole("button", { name: "전송" }).click();
  await expect(page.locator(".error-note")).toContainText("응답 생성 중 오류가 발생했습니다");
  await expect(page.getByLabel("메시지")).toBeEnabled();
});

test("새 대화는 진행 중인 스트림을 중단하고 화면을 비운다", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("메시지").fill("긴 응답 확인");
  await page.getByRole("button", { name: "전송" }).click();
  await expect(page.getByText("도구 실행 중")).toBeVisible();
  await page.getByRole("button", { name: "새 대화" }).click();
  await expect(page.getByText("무엇을 확인할까요?")).toBeVisible();
  await expect(page.getByText("현재 질문: 긴 응답 확인")).not.toBeVisible();
});

test("Multi-Agent 모드에서 계획과 Task 상태가 순서대로 보인다", async ({ page }) => {
  await page.goto("/");
  const singleId = await page.locator(".thread-bar code").textContent();
  await page.getByRole("button", { name: "Multi-Agent" }).click();
  const multiId = await page.locator(".thread-bar code").textContent();
  expect(multiId).not.toBe(singleId);
  await page.getByLabel("메시지").fill("가상 DB 절차");
  await page.getByRole("button", { name: "전송" }).click();

  await expect(page.getByRole("region", { name: "Supervisor 계획" })).toContainText("매뉴얼을 확인하고 답변합니다.");
  const tasks = page.locator(".task-card");
  await expect(tasks).toHaveCount(2);
  await expect(tasks.first()).toHaveClass(/task-in_progress/);
  await expect(tasks.first().locator(".task-tool summary")).toContainText("도구 실행 중");
  await expect(tasks.first().locator(".task-tool summary")).toContainText("도구 완료");
  await expect(tasks.first()).toHaveClass(/task-completed/);
  await expect(tasks.nth(1)).toHaveClass(/task-in_progress/);
  await expect(tasks.nth(1).getByLabel("task_2 진행 내용")).toContainText("답변 작성 중");
  await expect(tasks.nth(1)).toHaveClass(/task-completed/);
  await expect(page.locator(".final-answer")).toContainText("합성 Supervisor 답변");
  await expect(page.getByLabel("메시지")).toBeEnabled();

  await page.getByRole("button", { name: "Single Agent" }).click();
  await expect(page.locator(".thread-bar code")).toHaveText(singleId ?? "");
  await expect(page.getByText("무엇을 확인할까요?")).toBeVisible();
  await page.getByLabel("메시지").fill("단일 질문");
  await page.getByRole("button", { name: "전송" }).click();
  await expect(page.getByText(/합성 응답. 이전 질문: 없음/)).toBeVisible();
  await page.getByRole("button", { name: "Multi-Agent" }).click();
  await expect(page.locator(".thread-bar code")).toHaveText(multiId ?? "");
  await expect(page.getByText("무엇을 확인할까요?")).toBeVisible();
});

test("Supervisor 오류와 새 대화가 화면에 반영된다", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Multi-Agent" }).click();
  await page.getByLabel("메시지").fill("오류 확인");
  await page.getByRole("button", { name: "전송" }).click();
  await expect(page.locator(".error-note")).toContainText("응답 생성 중 오류가 발생했습니다");
  await expect(page.getByLabel("메시지")).toBeEnabled();
  const previousId = await page.locator(".thread-bar code").textContent();
  await page.getByRole("button", { name: "새 대화" }).click();
  await expect(page.locator(".thread-bar code")).not.toHaveText(previousId ?? "");
  await expect(page.getByText("무엇을 확인할까요?")).toBeVisible();
});
