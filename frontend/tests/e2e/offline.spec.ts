import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir, readFile } from "node:fs/promises";
import { signIn, workspace } from "./helpers";
test("historical actual results, evidence filtering and sanitized JSON export", async ({
  page,
}) => {
  await signIn(page);
  await workspace(page, "Research benchmarks", "Research benchmarks");
  await expect(
    page.getByText("Historical measurement, not live telemetry."),
  ).toBeVisible();
  const table = page.getByRole("region", { name: "Baseline comparison" });
  await expect(table.getByText("eraseproof", { exact: true })).toBeVisible();
  await page.getByLabel("Filter trials").fill("partial_order");
  await expect(
    page
      .getByRole("region", { name: "Research trials" })
      .getByText("partial_order", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("region", { name: "Research trials" })
    .getByRole("button", { name: "Inspect trial" })
    .click();
  await page.getByRole("button", { name: "Open finding" }).first().click();
  await expect(
    page.getByRole("heading", { name: "Failure investigator" }),
  ).toBeVisible();
  await expect(
    page.getByText("What the deletion system claimed"),
  ).toBeVisible();
  await expect(
    page
      .locator(".observation-card")
      .getByText("False success detected", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open evidence explorer" }).click();
  await expect(
    page.getByRole("heading", { name: "Evidence explorer" }),
  ).toBeVisible();
  await page.getByLabel("Evidence target").selectOption("orders");
  await page.locator(".evidence-record summary").first().click();
  await expect(page.locator(".evidence-body .json").first()).toContainText(
    "adapter_version",
  );
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download JSON report" }).click();
  const file = await download;
  const path = await file.path();
  const report = JSON.parse(await readFile(path!, "utf8"));
  expect(report.verification.id).toBeTruthy();
  expect(JSON.stringify(report)).not.toContain("@example.invalid");
  expect(report.evidence.length).toBeGreaterThan(0);
});
test("read-only role is enforced by the server, not just disabled buttons", async ({
  page,
}) => {
  await signIn(page);
  await workspace(page, "Customer data", "Customer data explorer");
  await expect(page.getByText(/Read-only session/)).toBeVisible();
  expect(
    await page
      .getByRole("button", { name: "Create customer", exact: true })
      .count(),
  ).toBe(0);
  const response = await page.request.get("/api/session");
  const { csrf } = await response.json();
  const denied = await page.request.post("/api/live/customer/v1/customers", {
    headers: { Origin: "http://127.0.0.1:8010", "X-CSRF-Token": csrf },
    data: {
      name: "Synthetic Unauthorized",
      email: "unauthorized@example.invalid",
    },
  });
  expect(denied.status()).toBe(403);
  const fault = await page.request.post("/api/research/jobs", {
    headers: { Origin: "http://127.0.0.1:8010", "X-CSRF-Token": csrf },
    data: {
      scenario: "false_ack_cache",
      seed: 101,
      acknowledge_isolated: true,
    },
  });
  expect(fault.status()).toBe(403);
  await workspace(page, "Fault injection studio", "Fault injection studio");
  await expect(
    page.getByRole("button", { name: "Run isolated scenario + verification" }),
  ).toBeDisabled();
});
test("explicit transport failure and timeout states never render successful live metrics", async ({
  page,
}) => {
  await signIn(page);
  await page.route("**/api/live/customer/v1/dashboard/snapshot", (route) =>
    route.fulfill({
      status: 504,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "Backend timed out; outcome is unknown.",
      }),
    }),
  );
  await page.getByRole("button", { name: "Refresh source data" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Backend timed out" }),
  ).toBeVisible();
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "—",
  );
  await workspace(page, "Research benchmarks", "Research benchmarks");
  await expect(
    page.getByText("Historical measurement, not live telemetry."),
  ).toBeVisible();
});
test("all workspaces at desktop and tablet sizes with real rendered screenshots", async ({
  page,
}) => {
  await signIn(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const views = [
    ["Command center", "Command center", "overview"],
    ["Data topology", "Follow the data, across every boundary", "topology"],
    ["Customer data", "Customer data explorer", "customers"],
    ["Deletion operations", "Deletion operations", "deletions"],
    ["Verification lab", "Verification lab", "verification"],
    ["Failure investigator", "Failure investigator", "investigator"],
    ["Fault injection studio", "Fault injection studio", "faults"],
    ["Research benchmarks", "Research benchmarks", "research"],
    ["Evidence explorer", "Evidence explorer", "evidence"],
  ];
  for (const [label, heading, id] of views) {
    await workspace(page, label, heading);
    await page.waitForTimeout(700);
    await mkdir("test-results/visual/desktop", { recursive: true });
    await page.screenshot({
      path: `test-results/visual/desktop/${id}.png`,
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
  await page.setViewportSize({ width: 1024, height: 768 });
  for (const [label, heading, id] of views) {
    await workspace(page, label, heading);
    await page.waitForTimeout(400);
    await mkdir("test-results/visual/tablet", { recursive: true });
    await page.screenshot({
      path: `test-results/visual/tablet/${id}.png`,
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
  await page.setViewportSize({ width: 768, height: 1024 });
  await workspace(page, "Research benchmarks", "Research benchmarks");
  await page.getByRole("button", { name: "Toggle color theme" }).click();
  await page.screenshot({
    path: "test-results/visual/tablet/research-light-768.png",
    fullPage: true,
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.keyboard.press("Tab");
  expect(errors).toEqual([]);
});

test("automated accessibility checks on real workspaces in dark and light themes", async ({
  page,
}) => {
  await signIn(page);
  for (const [label, heading] of [
    ["Data topology", "Follow the data, across every boundary"],
    ["Failure investigator", "Failure investigator"],
    ["Research benchmarks", "Research benchmarks"],
    ["Evidence explorer", "Evidence explorer"],
  ]) {
    await workspace(page, label, heading);
    await page.waitForTimeout(400);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      results.violations.map((v) => ({
        id: v.id,
        description: v.description,
        nodes: v.nodes.map((n) => n.target),
      })),
    ).toEqual([]);
  }
  await page.getByRole("button", { name: "Toggle color theme" }).click();
  const light = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    light.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
});
