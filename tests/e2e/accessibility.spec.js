const { test, expect } = require("@playwright/test");

test.describe("accessibility and keyboard UX", () => {
  test("mobile navigation opens, closes, and returns focus with keyboard", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto("/");

    const toggle = page.locator(".nav-toggle");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAccessibleName(/open main navigation/i);
    await toggle.focus();
    await page.keyboard.press("Enter");

    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(toggle).toHaveAccessibleName(/close main navigation/i);
    await expect(page.getByRole("navigation", { name: /main navigation/i })).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(toggle).toHaveAccessibleName(/open main navigation/i);
    await expect(toggle).toBeFocused();
  });

  test("registration errors are associated with invalid fields", async ({ page }) => {
    await page.goto("/accounts/register/");
    await page.getByRole("button", { name: /create buyer account/i }).click();

    const username = page.locator("[name='username']");
    await expect(username).toHaveAttribute("aria-invalid", "true");
    await expect(username).toHaveAttribute("aria-describedby", /id_username_error/);
    await expect(page.locator("#id_username_error")).toHaveCount(1);
    await expect(page.locator("#id_username_error")).toBeVisible();
  });

  test("skip link moves keyboard users to main content", async ({ page }) => {
    await page.goto("/");

    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: /skip to content/i })).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(page.locator("#main-content")).toBeFocused();
  });

  test("FAQ contents links and disclosures work with keyboard on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await page.goto("/faq/");

    const toc = page.getByRole("navigation", { name: /on this page/i });
    await expect(toc).toBeVisible();
    await toc.getByRole("link", { name: "Payments" }).click();
    await expect(page).toHaveURL(/#faq-payments$/);
    await expect(page.locator("#faq-payments")).toBeInViewport();

    const firstSummary = page.locator(".public-faq-list summary").first();
    await firstSummary.focus();
    await page.keyboard.press("Enter");
    await expect(firstSummary.locator("xpath=.." )).toHaveAttribute("open", "");
    await page.keyboard.press("Space");
    await expect(firstSummary.locator("xpath=.." )).not.toHaveAttribute("open", "");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
  });

  test("reduced motion preference disables reveal dependency", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/marketplace/");

    const hero = page.locator(".marketplace-heading");
    await expect(hero).toBeVisible();
    await expect(hero).toHaveCSS("transform", "none");
  });
});
