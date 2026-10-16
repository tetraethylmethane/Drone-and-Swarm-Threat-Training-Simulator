import { expect, test } from "@playwright/test";

import { newUserPage } from "./helpers";

test("trainees see competency tracking from their own results", async ({
  browser,
}) => {
  const page = await newUserPage(browser, "trainee2");
  await page.getByRole("link", { name: "My progress" }).click();
  await expect(
    page
      .getByRole("heading", { name: "Competency tracking" })
      .or(page.getByText("No scored sessions yet")),
  ).toBeVisible();
});

test("instructors see units, competency and can compare attempts", async ({
  browser,
}) => {
  const page = await newUserPage(browser, "instructor");
  await page.getByRole("link", { name: "Analytics" }).first().click();
  await expect(page.getByRole("heading", { name: "Units" })).toBeVisible();

  // Selecting a trainee replaces the unit summary with that trainee's competency tracking.
  const trainee = page.getByLabel("Trainee");
  const option = await trainee.locator("option").nth(1).getAttribute("value");
  await trainee.selectOption(option!);
  await expect(
    page.getByRole("heading", { name: "Competency tracking" }),
  ).toBeVisible();

  // Open a scored session and compare it with another attempt, if one exists.
  await page.getByRole("link", { name: "Review", exact: true }).first().click();
  await expect(
    page.getByRole("heading", { name: /After-action review/ }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Track decisions" }).click();
  await expect(
    page.getByRole("columnheader", { name: "Evidence" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Summary" }).click();
  const compare = page
    .getByRole("link", { name: "Compare", exact: true })
    .first();
  if (await compare.isVisible()) {
    await compare.click();
    await expect(
      page.getByRole("heading", { name: "Compare attempts" }),
    ).toBeVisible();
    await expect(
      page
        .getByText(/Identical exercise|Same scenario|Different scenarios/)
        .first(),
    ).toBeVisible();
  }
});
