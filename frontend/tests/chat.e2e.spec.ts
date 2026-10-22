import { expect, test } from "@playwright/test";

test("도구 상태, 토큰, 대화 ID와 새 대화를 화면에 반영한다", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "ICT 운영 지원 Agent" })).toBeVisible();
  const firstId = await page.locator(".thread-bar code").textContent();

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
  await expect(page.locator(".error-note")).toContainText("완료 신호 없이 끊어졌습니다");
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
