/**
 * Definition-of-done workflow, end to end through the real UI and API:
 * instructor assigns -> trainee completes the simulation -> events recorded -> reproducible
 * score -> dashboard shows saved results -> instructor reviews and exports.
 */
import { expect, test } from "@playwright/test";

import { newUserPage, unique } from "./helpers";

test("instructor assigns, trainee completes, instructor reviews and exports", async ({
  browser,
}) => {
  const title = unique("E2E perimeter");

  // --- Instructor creates an assignment ---------------------------------------
  const instructor = await newUserPage(browser, "instructor");
  await instructor.getByRole("link", { name: "Assignments" }).click();
  await instructor.getByRole("link", { name: "New assignment" }).click();
  await instructor
    .getByLabel("Scenario", { exact: true })
    .selectOption({ label: "Perimeter Awareness Basics (v1)" });
  await instructor.getByLabel("Title").fill(title);
  await instructor.getByLabel("Demo Trainee One (trainee1)").check();
  await instructor.getByRole("button", { name: "Assign exercise" }).click();
  await expect(instructor).toHaveURL(/\/instructor\/assignments$/);
  await expect(instructor.getByRole("cell", { name: title })).toBeVisible();

  // --- Trainee completes the exercise ------------------------------------------
  const trainee = await newUserPage(browser, "trainee1");
  await expect(
    trainee.getByRole("heading", { name: "My exercises" }),
  ).toBeVisible();
  const row = trainee.getByRole("row", { name: new RegExp(title) });
  await row.getByRole("link", { name: /Open|Resume/ }).click();
  await expect(
    trainee.getByRole("heading", { name: "Learning objectives" }),
  ).toBeVisible();
  await trainee.getByRole("button", { name: "Prepare exercise" }).click();
  await expect(trainee).toHaveURL(/\/exercise\//);
  await expect(trainee.getByText("Synthetic training data.")).toBeVisible();
  await trainee.getByRole("button", { name: "Start exercise" }).click();
  await expect(trainee.getByText("Running", { exact: true })).toBeVisible();

  // Wait for synthetic observations to arrive through the live feed.
  const firstTrack = trainee.getByLabel(/^Select TRK-\d{3}$/).first();
  await expect(firstTrack).toBeVisible({ timeout: 60_000 });
  const trackLabel = (await firstTrack.getAttribute("aria-label"))!.replace(
    "Select ",
    "",
  );
  await firstTrack.check();
  await trainee.getByLabel("Classification").selectOption("small_multirotor");
  await trainee.getByText("Low", { exact: true }).click();
  await trainee.getByRole("button", { name: "Submit classification" }).click();
  await expect(
    trainee.getByText(/Classification recorded for 1 track/),
  ).toBeVisible();
  await trainee
    .getByRole("button", { name: /Report to exercise control/ })
    .click();
  await expect(
    trainee.getByText("Report to exercise control recorded."),
  ).toBeVisible();
  await expect(
    trainee.getByRole("row", { name: new RegExp(trackLabel) }),
  ).toContainText("Small multirotor");

  // Pause and resume follow the server clock.
  await trainee.getByRole("button", { name: "Pause" }).click();
  await expect(trainee.getByText("Paused", { exact: true })).toBeVisible();
  await trainee.getByRole("button", { name: "Resume" }).click();
  await expect(trainee.getByText("Running", { exact: true })).toBeVisible();

  await trainee.getByRole("button", { name: "Finish exercise" }).click();
  await trainee.getByRole("button", { name: "Finish and score" }).click();
  await expect(trainee).toHaveURL(/\/sessions\/.+\/result$/);
  await expect(
    trainee.getByRole("heading", { name: /After-action review/ }),
  ).toBeVisible();
  await expect(
    trainee.getByRole("heading", { name: "Performance breakdown" }),
  ).toBeVisible();
  const sessionUrl = trainee.url();
  const overallText = await trainee.locator("p.text-4xl").innerText();
  expect(overallText).toMatch(/^\d+\.\d%$/);

  // Trainee sees their own decision in the track breakdown.
  await trainee.getByRole("tab", { name: "Track decisions" }).click();
  await expect(
    trainee.getByRole("row", { name: new RegExp(trackLabel) }),
  ).toContainText("Report to exercise control");

  // --- Instructor reviews, verifies and exports ----------------------------------
  await instructor.goto(new URL(sessionUrl).pathname);
  await expect(instructor.locator("p.text-4xl")).toHaveText(overallText); // dashboard shows the persisted value
  await instructor.getByRole("tab", { name: "Event timeline" }).click();
  await expect(
    instructor.getByRole("cell", { name: /classified Small multirotor/ }),
  ).toBeVisible();
  await instructor.getByLabel("Category").selectOption("ground_truth");
  await expect(
    instructor.getByRole("cell", { name: /appeared/ }).first(),
  ).toBeVisible();

  await instructor.getByRole("tab", { name: "Instructor review" }).click();
  await instructor.getByLabel("Review status").selectOption("reviewed");
  await instructor
    .getByLabel("Strengths", { exact: true })
    .fill("Prompt reporting of the first track.");
  await instructor
    .getByLabel(
      "Share strengths, improvements and focus objectives with the trainee",
    )
    .check();
  await instructor.getByRole("button", { name: "Save review" }).click();
  await expect(instructor.getByText("Review saved.")).toBeVisible();

  await instructor
    .getByRole("tab", { name: "Export and verification" })
    .click();
  await instructor
    .getByRole("button", { name: "Verify reproducibility" })
    .click();
  await expect(
    instructor.getByText("Reproduced", { exact: true }),
  ).toBeVisible();
  const [pdf] = await Promise.all([
    instructor.waitForEvent("download"),
    instructor.getByRole("button", { name: "Download PDF report" }).click(),
  ]);
  expect(pdf.suggestedFilename()).toMatch(/^drikr-aar-.+\.pdf$/);

  await instructor
    .getByRole("link", { name: "Sessions and reviews" })
    .first()
    .click();
  const [csv] = await Promise.all([
    instructor.waitForEvent("download"),
    instructor
      .getByRole("button", { name: "Export CSV (current filters)" })
      .click(),
  ]);
  expect(csv.suggestedFilename()).toBe("drikr-sessions.csv");

  // Trainee can now read the shared review (without private notes).
  await trainee.reload();
  await trainee.getByRole("tab", { name: "Instructor review" }).click();
  await expect(
    trainee.getByText("Prompt reporting of the first track."),
  ).toBeVisible();
  await expect(trainee.getByText("Private notes")).toHaveCount(0);
});
