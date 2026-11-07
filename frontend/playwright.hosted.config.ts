import { defineConfig } from "@playwright/test";
import { readFileSync } from "node:fs";
const credentials = JSON.parse(
  readFileSync("../work/hosted-ci/test-credentials.json", "utf8"),
);
process.env.HOSTED_TEST_PASSWORD = credentials.password;
export default defineConfig({
  testDir: "./tests/hosted",
  timeout: 180000,
  workers: 1,
  retries: 0,
  expect: { timeout: 30000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results-hosted/results.json" }],
  ],
  use: {
    baseURL: "https://demo.example.invalid",
    // The Python qualification separately verifies this private CI CA. This is not public HTTPS validation.
    ignoreHTTPSErrors: true,
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "off",
  },
});
