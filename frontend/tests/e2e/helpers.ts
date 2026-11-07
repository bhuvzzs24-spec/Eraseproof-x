import { expect, type Page } from "@playwright/test";
export async function signIn(
  page: Page,
  role: "readonly" | "operator" | "research" = "readonly",
) {
  await page.goto("/");
  await page.getByLabel("Access role").selectOption(role);
  const password = process.env[`DASHBOARD_${role.toUpperCase()}_PASSWORD`];
  if (!password)
    throw new Error("Generate .dashboard.env before browser tests");
  await page.getByLabel("Role password").fill(password);
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Command center", exact: true }),
  ).toBeVisible();
}
export async function workspace(page: Page, label: string, heading: string) {
  const menu = page.getByRole("button", { name: "Toggle navigation" });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("navigation", { name: "Engineering workspaces" })
    .getByRole("link", { name: label, exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: heading, exact: true }),
  ).toBeVisible();
}
