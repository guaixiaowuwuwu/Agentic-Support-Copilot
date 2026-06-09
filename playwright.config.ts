import { defineConfig, devices } from "@playwright/test";

const webPort = process.env.E2E_WEB_PORT ?? "3100";
const apiPort = process.env.E2E_API_PORT ?? "8100";
const baseURL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${webPort}`;
const apiBaseURL = process.env.E2E_API_BASE_URL ?? `http://127.0.0.1:${apiPort}`;
const reuseExistingServer = !process.env.CI && process.env.E2E_REUSE_SERVER !== "false";
const apiCommand = [
  "PY=\"$PWD/.venv/bin/python\"",
  "if [ ! -x \"$PY\" ]; then PY=python3; fi",
  "cd apps/api",
  `SUPPORT_COPILOT_STORE=memory SUPPORT_COPILOT_LLM_ENABLED=false "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`
].join("; ");

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: {
    timeout: 10_000
  },
  fullyParallel: false,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure"
  },
  webServer: [
    {
      command: `bash -lc '${apiCommand}'`,
      url: `${apiBaseURL}/api/health`,
      reuseExistingServer,
      timeout: 30_000
    },
    {
      command: `npm --workspace apps/web run dev -- --hostname 127.0.0.1 --port ${webPort}`,
      url: baseURL,
      reuseExistingServer,
      timeout: 60_000,
      env: {
        NEXT_PUBLIC_API_BASE: apiBaseURL,
        NEXT_PUBLIC_SUPPORT_COPILOT_LOCAL_IDENTITY_HEADERS: "true",
        NEXT_PUBLIC_SUPPORT_COPILOT_TENANT_ID: "acme",
        NEXT_PUBLIC_SUPPORT_COPILOT_TENANT_IDS: "acme"
      }
    }
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
