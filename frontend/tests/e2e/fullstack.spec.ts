import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { signIn, workspace } from "./helpers";
test("real customer propagation, deletion, independent verification and evidence export", async ({
  page,
}) => {
  await signIn(page, "operator");
  await expect(page.getByText("7/7 APIs ready")).toBeVisible();
  await workspace(
    page,
    "Data topology",
    "Follow the data, across every boundary",
  );
  await page
    .getByRole("button", {
      name: /Independent verifier Select to inspect scope/,
    })
    .click();
  await workspace(page, "Customer data", "Customer data explorer");
  await page
    .getByLabel("Fixture name")
    .fill(`Synthetic Browser Test ${Date.now()}`);
  await page
    .getByRole("button", { name: "Create customer", exact: true })
    .click();
  await expect(page.locator(".entity-id")).toHaveText(/^[a-f0-9-]{36}$/);
  await expect(
    page.locator(".location-list>div strong").filter({ hasText: /^Present$/i }),
  ).toHaveCount(4);
  await page
    .getByRole("button", { name: "Add synthetic order · $12.34" })
    .click();
  await expect(
    page.getByText("Order accepted by the real backend."),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Request deletion", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm request deletion", exact: true })
    .click();
  await expect(page).toHaveURL(/workspace=deletions&request=/);
  const requestId = new URL(page.url()).searchParams.get("request");
  expect(requestId).toBeTruthy();
  const details = page.locator(".panel").filter({
    has: page.getByRole("heading", {
      name: `Request ${requestId!.slice(0, 8)}`,
      exact: true,
    }),
  });
  await expect(
    details.getByText("Completed reported", { exact: true }),
  ).toBeVisible({ timeout: 60000 });
  await page.getByRole("button", { name: "Verify independently" }).click();
  await page
    .getByRole("button", { name: "Start verification", exact: true })
    .click();
  const report = page.locator(".panel").filter({
    has: page.getByRole("heading", { name: /^Independent report / }),
  });
  await expect(
    report
      .locator(".panel-head")
      .getByText("Verified absent · scoped", { exact: true }),
  ).toBeVisible({ timeout: 120000 });
  await expect(
    page
      .locator(".target-card .badge")
      .filter({ hasText: "Verified absent · scoped" }),
  ).toHaveCount(6);
  await page
    .getByRole("button", { name: "Inspect sanitized evidence" })
    .click();
  await page.getByLabel("Evidence target").selectOption("cache");
  await page.getByLabel("Evidence outcome").selectOption("VERIFIED_ABSENT");
  await page.locator(".evidence-record summary").first().click();
  await expect(page.locator(".evidence-body .json").first()).toContainText(
    "scope_complete",
  );
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download JSON report" }).click();
  const file = await pending;
  const json = JSON.parse(await readFile((await file.path())!, "utf8"));
  expect(json.verification.result).toBe("VERIFIED_ABSENT");
  expect(JSON.stringify(json)).not.toContain("@example.invalid");
  await page.screenshot({
    path: "test-results/visual/live-evidence.png",
    fullPage: true,
  });
});
test("authorized isolated false success uses the actual Phase 4 runner and independent stores", async ({
  page,
}) => {
  await signIn(page, "research");
  await workspace(page, "Fault injection studio", "Fault injection studio");
  await page
    .getByRole("button", { name: "Run isolated scenario + verification" })
    .click();
  await page
    .getByRole("checkbox", {
      name: "I confirm this is the isolated synthetic research stack.",
    })
    .check();
  const accepted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/research/jobs") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Authorize and execute", exact: true })
    .click();
  const response = await accepted;
  expect(response.status()).toBe(202);
  const job = await response.json();
  const execution = page.locator(".panel").filter({
    has: page.getByRole("heading", {
      name: "Research execution",
      exact: true,
    }),
  });
  await expect(execution.getByText("Completed", { exact: true })).toBeVisible({
    timeout: 200000,
  });
  await expect(
    execution.getByText("False success detected", { exact: true }),
  ).toBeVisible();
  await execution
    .getByRole("button", { name: "Investigate evidence" })
    .first()
    .click();
  await expect(
    page
      .locator(".claim-card")
      .getByText("Completed reported", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(".observation-card")
      .getByText("False success detected", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/visual/live-false-success.png",
    fullPage: true,
  });
  const detail = await page.request.get(`/api/research/jobs/${job.id}`);
  const actual = await detail.json();
  expect(actual.dataset.summary.methods.eraseproof.tp).toBeGreaterThan(0);
  expect(actual.dataset.summary.methods.api_ack.fn).toBeGreaterThan(0);
  expect(actual.dataset.trials[0].cleanup.status).toBe("RESTORED");
  expect(
    actual.dataset.trials[0].faults.some(
      (f: { state: string }) => f.state === "ACTIVATED",
    ),
  ).toBe(true);
});
test("direct synthetic write APIs reject missing operator credentials", async ({
  request,
}) => {
  const response = await request.post("http://127.0.0.1:8000/v1/customers", {
    data: {
      name: "Synthetic Unauthorized Direct",
      email: "unauthorized-direct@example.invalid",
    },
  });
  expect(response.status()).toBe(403);
});
