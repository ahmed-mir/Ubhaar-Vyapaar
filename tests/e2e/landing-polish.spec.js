const { test, expect } = require("@playwright/test");
const { dismissCookieBanner } = require("./helpers");

test("landing search is the primary action and fits supported viewports", async ({ page }) => {
  for (const [width, height] of [[320, 780], [390, 844], [768, 900], [1024, 900], [1366, 768], [1440, 900]]) {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    await dismissCookieBanner(page);

    await expect(page.locator("main h1")).toHaveCount(1);
    await expect(page.locator("main h1")).toContainText("small‑batch");
    await expect(page.getByRole("search")).toBeVisible();
    await expect(page.getByRole("searchbox", { name: "Search by product or process" })).toBeVisible();
    const searchButton = page.getByRole("button", { name: "Search capacity" });
    await expect(searchButton).toBeVisible();
    await expect(page.locator(".landing-hero-copy").getByRole("link", { name: "Register as Manufacturer" })).toBeVisible();
    await expect(page.locator(".landing-hero-copy")).toContainText("Buy Now on eligible fixed-price listings");
    await expect(page.locator(".landing-hero-copy")).toContainText("Request Quote for custom quantities and terms");
    await expect(page.getByText("No real funds are transferred").first()).toBeVisible();
    if ((await page.locator(".landing-featured").count()) === 0) {
      const emptyPreview = page.locator(".landing-preview-empty");
      await expect(emptyPreview).toBeVisible();
      await expect(emptyPreview.getByRole("link", { name: "Browse marketplace" })).toBeVisible();
    }

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

test("public journeys and account creation links match available workflows", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await dismissCookieBanner(page);

  await expect(page.getByText("Buy Now on eligible fixed-price listings", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("Request Quote for custom quantities and terms", { exact: false }).first()).toBeVisible();
  const paymentNotice = page.getByRole("note", { name: "Pilot payment status" });
  await expect(paymentNotice).toContainText("Razorpay Test Mode");
  await expect(paymentNotice).toContainText(/no real funds are transferred/i);

  const footerMarketplace = page.locator(".site-footer").getByRole("link", { name: "Browse marketplace" });
  await footerMarketplace.click();
  await expect(page).toHaveURL(/\/marketplace\/$/);
  await expect(page.locator("main h1")).toHaveCount(1);

  await page.goto("/");
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.locator(".nav-cta").click();
  await expect(page.getByRole("heading", { level: 1, name: "Choose your account type" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Create Buyer account" })).toHaveAttribute("href", /register/);
  await expect(page.getByRole("link", { name: "Register as Manufacturer" })).toHaveAttribute("href", /manufacturer/);

  await page.getByRole("link", { name: "Create Buyer account" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Create your buyer account" })).toBeVisible();
});
