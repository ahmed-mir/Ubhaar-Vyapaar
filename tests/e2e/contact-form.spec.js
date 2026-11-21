const { test, expect } = require("@playwright/test");

test.describe("contact form local QA", () => {
  test("contact support page submits and shows the post redirect success state", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 820 });
    await page.goto("/contact/");

    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    await expect(page.getByRole("heading", { level: 1, name: "Need help?" })).toBeVisible();
    await expect(page.getByText(/team will review it/i)).toBeVisible();
    const rejectCookies = page.getByRole("button", { name: /reject analytics/i });
    if (await rejectCookies.isVisible()) await rejectCookies.click();
    await page.getByLabel(/^Name:?$/).fill("Local QA Contact");
    await page.getByLabel(/^Email:?$/).fill("local-contact@example.test");
    await page.getByLabel(/I am a/).selectOption("OTHER");
    await page.getByLabel(/How can we help/).fill("Automated local contact form check.");
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page).toHaveURL(/\/contact\/$/);
    await expect(page.getByRole("status")).toContainText("Thanks for contacting Ubhaar-Vyapaar.");
    await expect(page.getByRole("status")).toContainText("Your message has been received.");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });

  test("contact page fits required responsive widths without horizontal overflow", async ({ page }) => {
    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/contact/");
      const rejectCookies = page.getByRole("button", { name: /reject analytics/i });
      if (await rejectCookies.isVisible()) await rejectCookies.click();

      await expect(page.getByRole("heading", { level: 1, name: "Need help?" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      if (width >= 1024) {
        const guidance = page.locator(".contact-guidance");
        const form = page.locator(".contact-form-section");
        const [guidanceBox, formBox] = await Promise.all([guidance.boundingBox(), form.boundingBox()]);
        expect(formBox.x).toBeLessThan(guidanceBox.x);
        expect(formBox.width).toBeGreaterThan(guidanceBox.width);
      }
    }
  });

  test("invalid email and blank message show field-associated errors", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 820 });
    await page.goto("/contact/");
    await page.getByLabel(/^Name:?$/).fill("Local QA Contact");
    await page.getByLabel(/^Email:?$/).fill("not-an-email");
    await page.getByLabel(/I am a/).selectOption("OTHER");
    await page.getByLabel(/How can we help/).fill("   ");
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page.locator("#id_email_error")).toBeVisible();
    await expect(page.locator("#id_message_error")).toBeVisible();
    await expect(page.getByLabel(/^Email:?$/)).toHaveAttribute("aria-invalid", "true");
    await expect(page.getByLabel(/How can we help/)).toHaveAttribute("aria-invalid", "true");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
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
    await expect(page.getByRole("alert").first()).toContainText("Please review the fields marked below");
  });
});
