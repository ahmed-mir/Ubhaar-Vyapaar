const { test, expect } = require("@playwright/test");

test.describe("contact form local QA", () => {
  test("360px contact page submits and shows the post redirect success state", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 820 });
    await page.goto("/contact/");

    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    const rejectCookies = page.getByRole("button", { name: /reject analytics/i });
    if (await rejectCookies.isVisible()) await rejectCookies.click();
    await page.screenshot({ path: "test-results/contact-form-360.png", fullPage: true });
    await page.getByLabel(/^Name:?$/).fill("Local QA Contact");
    await page.getByLabel(/^Email:?$/).fill("local-contact@example.test");
    await page.getByLabel(/I am a/).selectOption("OTHER");
    await page.getByLabel(/How can we help/).fill("Automated local contact form check.");
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page).toHaveURL(/\/contact\/$/);
    await expect(page.getByRole("status")).toContainText("Your message has been received.");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
  });

  test("1280px contact form remains balanced and does not overflow", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/contact/");
    const rejectCookies = page.getByRole("button", { name: /reject analytics/i });
    if (await rejectCookies.isVisible()) await rejectCookies.click();

    const guidance = page.locator(".contact-guidance");
    const form = page.locator(".contact-form-section");
    const [guidanceBox, formBox] = await Promise.all([guidance.boundingBox(), form.boundingBox()]);
    expect(guidanceBox).not.toBeNull();
    expect(formBox).not.toBeNull();
    expect(formBox.x).toBeGreaterThan(guidanceBox.x);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1280);
    await page.screenshot({ path: "test-results/contact-form-1280.png", fullPage: true });
  });

  test("keyboard tab order reaches every field and validation errors stay associated", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 820 });
    await page.goto("/contact/");

    const rejectCookies = page.getByRole("button", { name: /reject analytics/i });
    if (await rejectCookies.isVisible()) {
      await rejectCookies.focus();
      await page.keyboard.press("Enter");
    }

    const name = page.getByLabel(/^Name:?$/);
    await name.focus();
    await expect(name).toBeFocused();

    await page.keyboard.press("Tab");
    await expect(page.getByLabel(/^Email:?$/)).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel(/I am a/)).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel(/How can we help/)).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.locator(".contact-privacy-note a")).toBeFocused();
    await page.keyboard.press("Tab");
    const submit = page.getByRole("button", { name: "Send message" });
    await expect(submit).toBeFocused();
    await page.keyboard.press("Enter");

    const email = page.getByLabel(/^Email:?$/);
    await expect(email).toHaveAttribute("aria-invalid", "true");
    await expect(email).toHaveAttribute("aria-describedby", /id_email_error/);
    await expect(page.locator("#id_email_error")).toBeVisible();
    await expect(page.getByRole("alert").first()).toContainText("Please review the form errors");
  });
});
