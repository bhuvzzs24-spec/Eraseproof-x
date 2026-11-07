import { defineConfig, devices } from "@playwright/test";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
for (const name of [".env", ".dashboard.env"]) {
  const path = resolve("..", name);
  if (existsSync(path))
    for (const line of readFileSync(path, "utf8").split("\n")) {
      const index = line.indexOf("=");
      if (index > 0 && !line.startsWith("#")) {
        const key = line.slice(0, index);
        process.env[key] ??= line.slice(index + 1);
      }
    }
}
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 240000,
  expect: { timeout: 30000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { open: "never" }],
    ["json", { outputFile: "test-results/results.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:8010",
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 1000 },
    trace: "off",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      testMatch:
        process.env.RUN_FULLSTACK === "1"
          ? /.*\.spec\.ts/
          : /offline\.spec\.ts/,
    },
  ],
  webServer: {
    command: `${process.env.DASHBOARD_PYTHON || "python3"} scripts/start_dashboard.py`,
    cwd: resolve(".."),
    url: "http://127.0.0.1:8010",
    timeout: 120000,
    reuseExistingServer: !process.env.CI,
    env: {
      ...(process.env as Record<string, string>),
      DASHBOARD_ORIGIN: "http://127.0.0.1:8010",
      DASHBOARD_ENABLE_RESEARCH: process.env.RUN_FULLSTACK === "1" ? "1" : "0",
      DASHBOARD_RESEARCH_PROJECT:
        process.env.COMPOSE_PROJECT_NAME || "eraseproof-research",
      APP_ENV: "demo",
      ERASEPROOF_RESEARCH_FAULTS: process.env.RUN_FULLSTACK === "1" ? "1" : "0",
    },
  },
});
