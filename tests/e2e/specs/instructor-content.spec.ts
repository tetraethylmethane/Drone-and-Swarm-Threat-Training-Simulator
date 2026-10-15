import { expect, test } from "@playwright/test";

import { newUserPage } from "./helpers";

test("generate, validate, save and version a scenario", async ({ browser }) => {
  const page = await newUserPage(browser, "instructor");
  await page.getByRole("link", { name: "Scenarios" }).first().click();
  await page.getByRole("button", { name: "Generate scenario" }).click();
  const seed = String(100000 + Math.floor(Math.random() * 800000));
  await page.getByLabel("Seed").fill(seed);
  await page.getByLabel("Environment preset").selectOption("urban-night-clear");
  await page.getByLabel("Coordinated swarm").selectOption("yes");
  await page.getByRole("button", { name: "Generate draft" }).click();
  await expect(page).toHaveURL(/\/instructor\/scenarios\/new$/);
  await expect(page.getByLabel("Key")).toHaveValue(/^generated-\d{6}$/);

  await page.getByRole("button", { name: "Validate on server" }).click();
  await expect(page.getByText("Valid", { exact: true })).toBeVisible();
  await expect(page.getByText(/Test run \(seed/)).toBeVisible();

  // Introduce an error and see it reported before saving.
  await page.getByLabel("Visibility (km)").fill("10");
  await page.getByLabel("Weather").selectOption("fog");
  await expect(
    page.getByText("Fog requires visibility of 2 km or less"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Save scenario/ }),
  ).toBeDisabled();
  await page.getByLabel("Weather").selectOption("clear");

  await page.getByRole("button", { name: "Save scenario (version 1)" }).click();
  await expect(
    page.getByRole("heading", { name: /Generated exercise/ }),
  ).toBeVisible();
  await expect(page.getByText(/version 1 ·/)).toBeVisible();

  await page.getByRole("button", { name: "Run preview" }).click();
  await expect(
    page.getByRole("cell", { name: /Coordinated swarm/ }).first(),
  ).toBeVisible();

  await page.getByRole("button", { name: "Edit as new version" }).click();
  await page.getByLabel("Duration (s)").fill("360");
  await page.getByRole("button", { name: "Save as version 2" }).click();
  await expect(page.getByText(/version 2 ·/)).toBeVisible();
  await expect(page.getByRole("cell", { name: "v1" })).toBeVisible();
});

test("rubric weights must sum to one before a new version can be saved", async ({
  browser,
}) => {
  const page = await newUserPage(browser, "instructor");
  await page.getByRole("link", { name: "Scoring rubrics" }).click();
  await page.getByRole("link", { name: "Open" }).first().click();
  await page.getByRole("button", { name: "Edit as new version" }).click();
  await page.getByLabel("Recognition accuracy weight").fill("0.5");
  await expect(
    page.getByText("Weights must sum to 1.0 before saving."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save as new version" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Discard changes" }).click();
});

test("analytics shows only persisted results", async ({ browser }) => {
  const page = await newUserPage(browser, "instructor");
  await page.getByRole("link", { name: "Analytics" }).click();
  await page.getByLabel("From").fill("2099-01-01");
  await expect(
    page.getByText("No completed sessions match these filters"),
  ).toBeVisible();
});
