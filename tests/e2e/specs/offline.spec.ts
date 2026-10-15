/** Offline operation: the UI loads every asset and makes every request on its own origin. */
import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("no request leaves the application origin", async ({ page, baseURL }) => {
  const origin = new URL(baseURL!).origin;
  const external: string[] = [];
  page.on("request", (req) => {
    const url = req.url();
    if (
      !url.startsWith(origin) &&
      !url.startsWith("data:") &&
      !url.startsWith("blob:")
    )
      external.push(url);
  });
  await login(page, "trainee2");
  for (const path of [
    "/trainee",
    "/trainee/practice",
    "/trainee/history",
    "/account",
  ]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
  }
  await page.getByRole("link", { name: "Practice library" }).first().click();
  await page.getByRole("link", { name: "Open" }).first().click();
  await page.waitForLoadState("networkidle");
  expect(external).toEqual([]);
  const fonts = await page.evaluate(() =>
    [...document.fonts].map((f) => `${f.family}:${f.status}`),
  );
  expect(fonts.some((f) => f.startsWith("Inter"))).toBe(true);
});
