const { test, expect } = require("@playwright/test");
const { dismissCookieBanner } = require("./helpers");

test("landing search is the primary action and fits supported viewports", async ({ page }) => {
  for (const [width, height] of [[320, 780], [390, 844], [768, 900], [1366, 768], [1440, 900]]) {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    await dismissCookieBanner(page);

    await expect(page.locator("main h1")).toHaveCount(1);
    await expect(page.locator("main h1")).toContainText("small‑batch");
    await expect(page.getByRole("search")).toBeVisible();
    await expect(page.getByRole("searchbox", { name: "Search by product or process" })).toBeVisible();
    const searchButton = page.getByRole("button", { name: "Search capacity" });
    await expect(searchButton).toBeVisible();
    await expect(page.locator(".landing-hero-copy").getByRole("link", { name: "I'm a manufacturer" })).toBeVisible();

    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    if (width === 1366) {
      const buttonBounds = await searchButton.boundingBox();
      expect(buttonBounds.y + buttonBounds.height).toBeLessThanOrEqual(height);
    }
  }

  const searchbox = page.getByRole("searchbox", { name: "Search by product or process" });
  await searchbox.fill("packaging");
  await searchbox.press("Enter");
  await expect(page).toHaveURL(/\/marketplace\/\?q=packaging$/);
});
