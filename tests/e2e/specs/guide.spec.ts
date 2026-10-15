import { expect, test } from "@playwright/test";

import { PASSWORD } from "./helpers";

test("first-time trainees get a guide and step-by-step hints", async ({
  page,
}) => {
  // Sign in directly: while the welcome dialog is open it (correctly) hides the page behind it.
  await page.goto("/login");
  await page.getByLabel("Username").fill("trainee1");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  const welcome = page.getByRole("dialog", {
    name: "Welcome to the training simulator",
  });
  await expect(welcome).toBeVisible();
  await welcome.getByRole("link", { name: "Read the full guide" }).click();
  await expect(
    page.getByRole("heading", { name: "How to play", level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Coordinated swarm" }),
  ).toBeVisible();

  // Shown once only.
  await page.goto("/trainee");
  await expect(
    page.getByRole("heading", { name: "My exercises" }),
  ).toBeVisible();
  await expect(welcome).toBeHidden();

  // The Next step bar follows the exercise.
  await page.getByRole("link", { name: "Practice library" }).first().click();
  await page.getByRole("link", { name: "Open" }).first().click();
  await page
    .getByRole("button", { name: /Prepare exercise|Resume exercise/ })
    .click();
  const hint = page.getByRole("status").filter({ hasText: "Next step" });
  const start = page.getByRole("button", { name: "Start exercise" });
  await expect(
    start.or(page.getByText("Running", { exact: true })),
  ).toBeVisible();
  if (await start.isVisible()) {
    await expect(hint).toContainText("Press Start exercise");
    await start.click();
  }
  await expect(hint).toContainText(/Select a track: tick TRK-\d{3}/, {
    timeout: 60_000,
  });
  await page
    .getByLabel(/^Select TRK-\d{3}$/)
    .first()
    .check();
  await expect(hint).toContainText(/Classify TRK-\d{3}/);
  await page.getByRole("button", { name: "How to play" }).click();
  await expect(
    page.getByRole("heading", { name: "Step by step" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Finish exercise" }).click();
  await page.getByRole("button", { name: "Finish and score" }).click();
  await expect(
    page.getByRole("heading", { name: "Performance breakdown" }),
  ).toBeVisible();
});
