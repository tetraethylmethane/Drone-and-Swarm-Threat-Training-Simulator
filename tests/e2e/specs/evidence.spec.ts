import { expect, test } from "@playwright/test";

import { newUserPage } from "./helpers";

// Works on an empty database: each check accepts the explicit empty state. The AAR evidence column is
// covered by full-workflow.spec.ts, which creates its own scored session.

test("trainees see competency tracking from their own results", async ({
  browser,
}) => {
  const page = await newUserPage(browser, "trainee2");
  await page.getByRole("link", { name: "My progress" }).click();
  await expect(
    page.getByRole("heading", { name: "Competency tracking" }),
  ).toBeVisible();
});

test("instructors see the unit summary and a trainee's competency tracking", async ({
  browser,
}) => {
  const page = await newUserPage(browser, "instructor");
  await page.getByRole("link", { name: "Analytics" }).first().click();
  await expect(page.getByRole("heading", { name: "Units" })).toBeVisible();
  const trainee = page.getByLabel("Trainee");
  const option = await trainee.locator("option").nth(1).getAttribute("value");
  await trainee.selectOption(option!);
  await expect(
    page.getByRole("heading", { name: "Competency tracking" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Units" })).toBeHidden();
});

test("the compare page explains how comparable two attempts are", async ({
  browser,
}) => {
  const page = await newUserPage(browser, "trainee2");
  const sessions = await page.evaluate(async () => {
    const r = await fetch("/api/v1/analytics/progress");
    return ((await r.json()).points as { session_id: string }[]).map(
      (p) => p.session_id,
    );
  });
  test.skip(sessions.length < 2, "needs two scored sessions for this trainee");
  await page.goto(
    `/sessions/compare?a=${sessions[0]}&b=${sessions[sessions.length - 1]}`,
  );
  await expect(
    page.getByRole("heading", { name: "Compare attempts" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      /^(Identical exercise|Same scenario, different tracks|Different scenarios)$/,
    ),
  ).toBeVisible();
});
