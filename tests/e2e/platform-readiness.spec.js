const { test, expect } = require("@playwright/test");

test.describe("platform readiness", () => {
  test("cookie choices persist and can be changed from footer", async ({ page }) => {
    await page.goto("/");

    const banner = page.locator("[data-cookie-consent]");
    await expect(banner).toBeVisible();

    const rejectButton = page.getByRole("button", { name: /reject analytics/i });
    await rejectButton.focus();
    await page.keyboard.press("Enter");
    await expect(banner).toBeHidden();

    await page.reload();
    await expect(banner).toBeHidden();

    const settingsButton = page.getByRole("button", { name: /cookie settings/i });
    await settingsButton.focus();
    await page.keyboard.press("Enter");
    await expect(banner).toBeVisible();
    const analyticsCheckbox = page.getByLabel(/optional product analytics/i);
    await analyticsCheckbox.focus();
    await page.keyboard.press("Space");
    const saveButton = page.getByRole("button", { name: /save preferences/i });
    await saveButton.focus();
    await page.keyboard.press("Enter");

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
