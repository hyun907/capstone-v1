import path from "node:path";

import { defineConfig } from "@playwright/test";

export default defineConfig({
  testMatch: "**/*.e2e.spec.ts",
  use: { baseURL: "http://127.0.0.1:3000", browserName: "chromium" },
  webServer: [
    {
      command: "uv run --locked --extra backend uvicorn streaming_demo_app:app --app-dir tests --host 127.0.0.1 --port 8765",
      cwd: path.resolve(process.cwd(), ".."),
      env: { PYTHONPATH: path.resolve(process.cwd(), "..") },
      url: "http://127.0.0.1:8765/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3000",
      env: { NEXT_PUBLIC_BACKEND_URL: "http://127.0.0.1:8765" },
      url: "http://127.0.0.1:3000",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
