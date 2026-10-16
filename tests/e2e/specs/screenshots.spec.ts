/**
 * Captures reference screenshots of key screens for design review (docs/design/screens).
 * Run explicitly: npx playwright test screenshots --grep @screens
 */
import { expect, test } from "@playwright/test";

import { login, newUserPage } from "./helpers";

const OUT = process.env.SCREENSHOT_DIR ?? "../../docs/design/screens";

test("capture key screens @screens", async ({ browser, page }) => {
  test.skip(!process.env.CAPTURE_SCREENS, "set CAPTURE_SCREENS=1 to capture");
  await page.goto("/login");
  await page.screenshot({ path: `${OUT}/01-login.png` });

  const trainee = await newUserPage(browser, "trainee2");
  await trainee.goto("/trainee/how-to-play");
  await trainee.screenshot({
    path: `${OUT}/16-how-to-play.png`,
    fullPage: true,
  });
  await trainee.goto("/trainee");
  await trainee.screenshot({
    path: `${OUT}/02-trainee-home.png`,
    fullPage: true,
  });
  await trainee.getByRole("link", { name: "Practice library" }).first().click();
  await trainee.getByRole("link", { name: "Open" }).first().click();
  await trainee.screenshot({ path: `${OUT}/03-briefing.png`, fullPage: true });
  await trainee
    .getByRole("button", { name: /Prepare exercise|Resume exercise/ })
    .click();
  await expect(
    trainee.getByText(/^(Ready to start|Running|Paused)$/),
  ).toBeVisible();
  const start = trainee.getByRole("button", { name: "Start exercise" });
  if (await start.isVisible()) {
    await trainee.screenshot({ path: `${OUT}/04a-exercise-before-start.png` });
    await start.click();
  }
  await expect(trainee.getByLabel(/^Select TRK-\d{3}$/).first()).toBeVisible({
    timeout: 60_000,
  });
  await trainee.waitForTimeout(15_000);
  await trainee
    .getByLabel(/^Select TRK-\d{3}$/)
    .first()
    .check();
  await trainee.screenshot({
    path: `${OUT}/04-exercise-3d.png`,
    fullPage: true,
  });
  await trainee.getByRole("button", { name: "Plan view" }).click();
  await trainee.screenshot({ path: `${OUT}/05-exercise-plan.png` });
  await trainee.getByRole("button", { name: "Finish exercise" }).click();
  await trainee.getByRole("button", { name: "Finish and score" }).click();
  await expect(
    trainee.getByRole("heading", { name: "Performance breakdown" }),
  ).toBeVisible();
  await trainee.screenshot({
    path: `${OUT}/06-aar-summary.png`,
    fullPage: true,
  });
  await trainee.getByRole("tab", { name: "Error analysis" }).click();
  await trainee.screenshot({
    path: `${OUT}/07-aar-errors.png`,
    fullPage: true,
  });
  await trainee.getByRole("tab", { name: "Summary" }).click();
  const compare = trainee
    .getByRole("link", { name: "Compare", exact: true })
    .first();
  if (await compare.isVisible()) {
    await compare.click();
    await expect(
      trainee.getByRole("heading", { name: "Compare attempts" }),
    ).toBeVisible();
    await trainee.screenshot({
      path: `${OUT}/18-compare-attempts.png`,
      fullPage: true,
    });
  }
  await trainee.goto("/trainee/history");
  await expect(
    trainee.getByRole("heading", { name: "Competency tracking" }),
  ).toBeVisible();
  await trainee
    .getByRole("heading", { name: "Competency tracking" })
    .scrollIntoViewIfNeeded();
  await trainee.screenshot({
    path: `${OUT}/17-competency.png`,
    fullPage: true,
  });

  const instructor = await newUserPage(browser, "instructor");
  await instructor.screenshot({
    path: `${OUT}/08-instructor-overview.png`,
    fullPage: true,
  });
  await instructor.getByRole("link", { name: "Analytics" }).first().click();
  await instructor.waitForLoadState("networkidle");
  await instructor.screenshot({
    path: `${OUT}/09-analytics.png`,
    fullPage: true,
  });
  await instructor.goto("/instructor/scenarios/new");
  await instructor.screenshot({ path: `${OUT}/10-scenario-editor.png` });

  await login(page, "admin");
  await page.getByRole("link", { name: "Audit log" }).click();
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: `${OUT}/11-audit.png` });
  await page.goto("/admin/system");
  await page.getByRole("button", { name: "Check last 50 sessions" }).click();
  await expect(page.getByText(/sessions reproduced/)).toBeVisible({
    timeout: 60_000,
  });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `${OUT}/19-system-health.png`,
    fullPage: true,
  });
  await page.goto("/account");
  await page.waitForLoadState("networkidle");
  await page.screenshot({
    path: `${OUT}/12-account-security.png`,
    fullPage: true,
  });
  await page.goto("/admin/settings");
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(
    page.getByText("Expired sign-in records", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0)); // the sidebar is sticky
  await page.screenshot({
    path: `${OUT}/13-settings-mfa-retention.png`,
    fullPage: true,
  });
});
