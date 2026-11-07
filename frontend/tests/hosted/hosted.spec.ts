import { test, expect } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";

test("public read-only demo uses actual hosted APIs and cannot mutate", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Explore read-only demonstration" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Command center", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("7/7 APIs ready")).toBeVisible();
  await page.getByRole("link", { name: "Customer data", exact: true }).click();
  await expect(page.getByText(/Read-only session/)).toBeVisible();
  const { csrf } = await (await page.request.get("/api/session")).json();
  const headers = {
    Origin: "https://demo.example.invalid",
    "X-CSRF-Token": csrf,
  };
  expect(
    (
      await page.request.post("/api/live/deletion/v1/deletions", {
        headers,
        data: {},
      })
    ).status(),
  ).toBe(403);
  expect(
    (
      await page.request.post("/api/research/jobs", {
        headers,
        data: {
          scenario: "false_ack_cache",
          seed: 101,
          acknowledge_isolated: true,
        },
      })
    ).status(),
  ).toBe(403);
  await page
    .getByRole("link", { name: "Research benchmarks", exact: true })
    .click();
  await expect(
    page.getByText("Historical measurement, not live telemetry."),
  ).toBeVisible();
  await mkdir("test-results-hosted/visual", { recursive: true });
  await page.screenshot({
    path: "test-results-hosted/visual/public-research.png",
    fullPage: true,
  });
});

test("per-account operator performs real hosted deletion and sanitized export", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Account username").fill("owner");
  await page.getByLabel("Access role").selectOption("operator");
  await page
    .getByLabel("Account password")
    .fill(process.env.HOSTED_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(page.getByText("7/7 APIs ready")).toBeVisible();
  await page.getByRole("link", { name: "Customer data", exact: true }).click();
  await page
    .getByLabel("Fixture name")
    .fill(`Synthetic Hosted Browser ${Date.now()}`);
  await page
    .getByRole("button", { name: "Create customer", exact: true })
    .click();
  await expect(page.locator(".entity-id")).toHaveText(/^[a-f0-9-]{36}$/);
  await expect(
    page.locator(".location-list>div strong").filter({ hasText: /^Present$/i }),
  ).toHaveCount(4);
  await page
    .getByRole("button", { name: "Request deletion", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm request deletion", exact: true })
    .click();
  await page.waitForURL((url) => !!url.searchParams.get("request"));
  const requestId = new URL(page.url()).searchParams.get("request")!;
  const detail = page.locator(".panel").filter({
    has: page.getByRole("heading", {
      name: `Request ${requestId.slice(0, 8)}`,
      exact: true,
    }),
  });
  await expect(
    detail.getByText("Completed reported", { exact: true }),
  ).toBeVisible({ timeout: 60000 });
  await page.getByRole("button", { name: "Verify independently" }).click();
  await page
    .getByRole("button", { name: "Start verification", exact: true })
    .click();
  await expect(
    page
      .locator(".target-card .badge")
      .filter({ hasText: "Verified absent · scoped" }),
  ).toHaveCount(6, { timeout: 120000 });
  await page
    .getByRole("button", { name: "Inspect sanitized evidence" })
    .click();
  await expect(page.getByLabel("Evidence run")).not.toHaveValue("");
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download JSON report" }).click();
  const result = await pending;
  const report = JSON.parse(await readFile((await result.path())!, "utf8"));
  expect(report.verification.result).toBe("VERIFIED_ABSENT");
  expect(JSON.stringify(report)).not.toContain("@example.invalid");
  await page.screenshot({
    path: "test-results-hosted/visual/hosted-evidence.png",
    fullPage: true,
  });
});
