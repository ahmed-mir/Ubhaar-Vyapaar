const { test, expect } = require("@playwright/test");

test.describe("platform readiness", () => {
  test("cookie choices persist and can be changed from footer", async ({ page }) => {
    await page.goto("/");

    const banner = page.locator("[data-cookie-consent]");
    await expect(banner).toBeVisible();

    await page.getByRole("button", { name: /reject analytics/i }).click();
    await expect(banner).toBeHidden();

    await page.reload();
    await expect(banner).toBeHidden();

    await page.getByRole("button", { name: /cookie settings/i }).click();
    await expect(banner).toBeVisible();
    await page.getByLabel(/analytics/i).check();
    await page.getByRole("button", { name: /save preferences/i }).click();

    const cookie = (await page.context().cookies()).find(
      (item) => item.name === "uv_cookie_preferences"
    );

    expect(decodeURIComponent(cookie.value)).toContain('"analytics":true');
  });

  test("analytics script is absent when no measurement id is configured", async ({ page }) => {
    await page.goto("/");

    await expect(page.locator('script[src*="googletagmanager.com/gtag/js"]')).toHaveCount(0);
  });
});
