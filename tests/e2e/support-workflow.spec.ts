import { expect, test } from "@playwright/test";

const apiBaseURL = process.env.E2E_API_BASE_URL ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? "8100"}`;

function idFromURL(url: string, pattern: RegExp): string {
  const match = pattern.exec(url);
  expect(match, `Expected URL to match ${pattern}: ${url}`).not.toBeNull();
  return match?.[1] ?? "";
}

test("local role selection routes each role to its workspace", async ({ page }) => {
  const cases = [
    {
      button: /客服专员/,
      heading: "工单",
      url: /\/$/
    },
    {
      button: /审批人/,
      heading: "审批队列",
      url: /\/approvals$/
    },
    {
      button: /知识库管理员/,
      heading: "知识库",
      url: /\/knowledge$/
    },
    {
      button: /^管理员 /,
      heading: "审计日志",
      url: /\/audit$/
    }
  ];

  for (const roleCase of cases) {
    await page.context().clearCookies();
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "选择登录角色", exact: true })).toBeVisible();
    await page.getByRole("button", { name: roleCase.button }).click();
    await expect(page).toHaveURL(roleCase.url);
    await expect(page.getByRole("heading", { name: roleCase.heading, exact: true })).toBeVisible();
  }
});

test("direct restricted and missing resources show explicit states", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "选择登录角色", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /客服专员/ }).click();
  await expect(page.getByRole("heading", { name: "工单", exact: true })).toBeVisible();

  await page.goto("/knowledge");
  await expect(page.getByRole("heading", { name: "知识库", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "权限不足", exact: true })).toBeVisible();
  await expect(page.getByText("当前角色不能打开这个工作台。")).toBeVisible();

  await page.goto(`/tickets/missing-${Date.now().toString(36)}`);
  await expect(page.getByRole("heading", { name: "未找到资源", exact: true })).toBeVisible();
  await expect(page.getByText("该资源不存在，或当前租户无权查看。")).toBeVisible();
  await expect(page.getByText("demo-ticket-api-401")).toHaveCount(0);
});

test("admin can open audit and system configuration", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "选择登录角色", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^管理员 / }).click();

  await expect(page).toHaveURL(/\/audit$/);
  await expect(page.getByRole("heading", { name: "审计日志", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /系统/ })).toBeVisible();

  await page.getByRole("link", { name: /系统/ }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole("heading", { name: "管理员", exact: true })).toBeVisible();
  await expect(page.getByText("身份模式")).toBeVisible();
});

test("support agent workflow covers ticket creation, run start, approval, language toggle, and trace", async ({
  page,
  request
}) => {
  const health = await request.get(`${apiBaseURL}/api/health`);
  expect(health.ok()).toBeTruthy();
  expect(await health.json()).toMatchObject({
    status: "ok"
  });

  const suffix = Date.now().toString(36);
  const subject = `E2E API 401 ${suffix}`;
  const customer = `E2E Customer ${suffix}`;
  const description = `客户说 API 报 401，帮我排查并回复。request_id=req_e2e_${suffix}`;

  await test.step("switch language without losing dashboard rendering", async () => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "选择登录角色", exact: true })).toBeVisible();
    await page.getByRole("button", { name: /客服专员/ }).click();
    await expect(page.getByRole("heading", { name: "工单", exact: true })).toBeVisible();

    await page.getByRole("button", { name: "切换语言" }).click();
    await expect(page.getByRole("heading", { name: "Tickets", exact: true })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Subject", exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Switch language" }).click();
    await expect(page.getByRole("heading", { name: "工单", exact: true })).toBeVisible();
  });

  let ticketId = "";
  await test.step("create a ticket and verify the automatic first run reaches approval", async () => {
    await page.getByRole("textbox", { name: "客户", exact: true }).fill(customer);
    await page.getByRole("textbox", { name: "主题", exact: true }).fill(subject);
    await page.getByRole("textbox", { name: "描述", exact: true }).fill(description);
    await page.getByRole("button", { name: "创建 + 运行" }).click();

    await expect(page).toHaveURL(/\/tickets\/[^/]+$/);
    ticketId = idFromURL(page.url(), /\/tickets\/([^/?#]+)$/);
    await expect(page.getByRole("heading", { name: subject, exact: true })).toBeVisible();
    await expect(page.getByText(customer, { exact: true })).toBeVisible();
    await expect(page.getByText("待审批").first()).toBeVisible();
    await expect(page.getByText("human_approval")).toBeVisible();
    await expect(page.getByText("API Authentication Runbook")).toBeVisible();
  });

  let runId = "";
  await test.step("start an agent run from the ticket detail page and inspect trace", async () => {
    await page.getByRole("button", { name: "启动运行" }).click();

    await expect(page).toHaveURL(/\/runs\/[^/]+\/trace$/);
    runId = idFromURL(page.url(), /\/runs\/([^/]+)\/trace$/);
    await expect(page.getByRole("heading", { name: "运行追踪", exact: true })).toBeVisible();
    await expect(page.getByText("待审批").first()).toBeVisible();

    const timeline = page.locator("ol.timeline");
    for (const stepName of ["triage", "retrieval", "tool_call_optional", "verifier", "human_approval"]) {
      await expect(timeline.getByText(stepName, { exact: true })).toBeVisible();
    }

    await expect(page.getByRole("heading", { name: "校验器" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "工具调用" })).toBeVisible();
    await expect(page.getByText("log_search")).toBeVisible();
    await expect(page.getByText("db_read")).toBeVisible();
    await expect(page.getByRole("heading", { name: "检索证据" })).toBeVisible();
    await expect(page.getByText("API Authentication Runbook")).toBeVisible();
    await expect(page.getByText("kb://api/authentication-runbook")).toBeVisible();
  });

  await test.step("approve the target run from the approval queue", async () => {
    await page.getByRole("combobox", { name: "切换角色" }).selectOption("approver");
    await expect(page.getByRole("heading", { name: "审批队列", exact: true })).toBeVisible();

    const approvalCard = page.locator("article.surface").filter({
      has: page.locator(`a[href="/runs/${runId}/trace"]`)
    });
    await expect(approvalCard).toBeVisible();
    await expect(approvalCard.getByText(customer)).toBeVisible();
    await approvalCard.getByRole("button", { name: "批准" }).click();

    await expect(page.locator(`a[href="/runs/${runId}/trace"]`)).toHaveCount(0);
  });

  await test.step("show the approved final reply on the ticket", async () => {
    await page.getByRole("combobox", { name: "切换角色" }).selectOption("support_agent");
    await page.goto(`/tickets/${ticketId}`);
    await expect(page.getByRole("heading", { name: subject, exact: true })).toBeVisible();
    const finalReplySection = page.locator("section.surface").filter({
      has: page.getByRole("heading", { name: "最终回复", exact: true })
    });
    await expect(finalReplySection).toBeVisible();
    await expect(page.getByText("已回复").first()).toBeVisible();
    await expect(finalReplySection.getByText("引用来源：")).toBeVisible();
    await expect(finalReplySection.getByText("API Authentication Runbook")).toBeVisible();
  });
});
