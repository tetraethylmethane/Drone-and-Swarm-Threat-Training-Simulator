import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { login, newUserPage, PASSWORD } from "./helpers";

test("unauthenticated users are sent to sign-in", async ({ page }) => {
  await page.goto("/instructor/scenarios");
  await expect(page).toHaveURL(/\/login$/);
  const res = await page.request.get("/api/v1/sessions");
  expect(res.status()).toBe(401);
});

test("generic error on bad credentials", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("instructor");
  await page.getByLabel("Password").fill("definitely-wrong-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(/Invalid username or password/)).toBeVisible();
});

test("trainee cannot reach instructor or administrator functions", async ({
  browser,
}) => {
  const page = await newUserPage(browser, "trainee2");
  await page.goto("/admin/users");
  await expect(page).toHaveURL(/\/trainee$/);
  await page.goto("/instructor/scenarios");
  await expect(page).toHaveURL(/\/trainee$/);
  // The backend refuses regardless of what the UI shows.
  const status = await page.evaluate(
    async () => (await fetch("/api/v1/users")).status,
  );
  expect(status).toBe(403);
  const csrfless = await page.evaluate(
    async () =>
      (
        await fetch("/api/v1/sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        })
      ).status,
  );
  expect(csrfless).toBe(403);
});

test("administrator pages work and the audit chain verifies", async ({
  browser,
}) => {
  const page = await newUserPage(browser, "admin");
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();
  await page.getByRole("link", { name: "Audit log" }).click();
  await page.getByRole("button", { name: "Verify chain" }).click();
  await expect(page.getByText(/Chain intact/)).toBeVisible();
  await page.getByRole("link", { name: "System health" }).click();
  await expect(page.getByText("simcore-1.0.0")).toBeVisible();
  await expect(page.getByText("None", { exact: true }).first()).toBeVisible(); // no external runtime dependencies
});

test.describe("accessibility", () => {
  for (const [name, user, path] of [
    ["login", null, "/login"],
    ["trainee home", "trainee2", "/trainee"],
    ["practice library", "trainee2", "/trainee/practice"],
    ["instructor overview", "instructor", "/instructor"],
    ["scenario list", "instructor", "/instructor/scenarios"],
    ["assignment form", "instructor", "/instructor/assignments/new"],
    ["admin users", "admin", "/admin/users"],
  ] as const) {
    test(`${name} has no serious or critical axe violations`, async ({
      page,
    }) => {
      if (user) await login(page, user);
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa"])
        .analyze();
      const serious = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical",
      );
      expect(
        serious.map(
          (v) => `${v.id}: ${v.nodes.length} node(s) ${v.nodes[0]?.target}`,
        ),
      ).toEqual([]);
    });
  }

  test("keyboard navigation and visible focus on sign-in", async ({ page }) => {
    await page.goto("/login");
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Username")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Password")).toBeFocused();
    await page.keyboard.press("Tab");
    const submit = page.getByRole("button", { name: "Sign in" });
    await expect(submit).toBeFocused();
    const ring = await submit.evaluate((el) => getComputedStyle(el).boxShadow);
    expect(ring).not.toBe("none");
  });

  test("skip link and keyboard-operable navigation", async ({ page }) => {
    await login(page, "instructor");
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Skip to main content" });
    await expect(skip).toBeFocused();
    await page.keyboard.press("Enter");
    await page.getByRole("link", { name: "Scenarios" }).first().focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/instructor\/scenarios$/);
  });
});

test("no monospace fonts in the product interface", async ({ browser }) => {
  const page = await newUserPage(browser, "instructor");
  for (const path of [
    "/instructor",
    "/instructor/scenarios",
    "/instructor/rubrics",
    "/instructor/analytics",
  ]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const mono = await page.evaluate(() =>
      [...document.querySelectorAll("body *")]
        .filter((el) =>
          /mono|courier|consolas/i.test(getComputedStyle(el).fontFamily),
        )
        .map((el) => el.tagName),
    );
    expect(mono, path).toEqual([]);
  }
});

test("administrators must use MFA and sign in with a code", async ({
  browser,
}) => {
  // The first sign-in enrols if needed (helpers.login); the second must ask for a code.
  const first = await newUserPage(browser, "admin");
  await first.context().close();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(
    page.getByRole("heading", { name: "Verification code" }),
  ).toBeVisible();
  await page.getByLabel("Code").fill("000000");
  await page.getByRole("button", { name: "Verify and sign in" }).click();
  await expect(
    page.getByText("The verification code is not valid"),
  ).toBeVisible();
  await ctx.close();

  const admin = await newUserPage(browser, "admin");
  const row = admin
    .getByRole("row")
    .filter({ has: admin.getByRole("cell", { name: "admin", exact: true }) });
  await expect(row.getByText("MFA on")).toBeVisible();
  await admin.getByRole("link", { name: "Settings" }).click();
  await expect(admin.getByLabel("Require for administrators")).toBeChecked();
  await expect(
    admin.getByRole("heading", { name: "Data retention" }),
  ).toBeVisible();
  await admin.getByRole("button", { name: "Preview" }).click();
  await expect(
    admin.getByText("Expired sign-in records", { exact: true }),
  ).toBeVisible();
});
