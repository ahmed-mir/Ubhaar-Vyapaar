const { test, expect } = require("@playwright/test");
const { dismissCookieBanner } = require("./helpers");

test.describe("early-access waitlist", () => {
  test("fits at 360px, supports keyboard submission, and shows neutral success", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 900 });
    await page.goto("/");
    await dismissCookieBanner(page);

    const form = page.locator(".waitlist-form");
    const email = page.getByLabel("Email");
    const role = page.getByLabel("I am a...");
    const note = page.getByLabel("Optional note");
    const submit = page.getByRole("button", { name: "Join early access" });

    await expect(form).toBeVisible();
    await expect(email).toBeVisible();
    await expect(role).toBeVisible();
    await expect(note).toBeVisible();
    await expect(submit).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);

    await email.focus();
    await email.fill(`waitlist-${Date.now()}@example.test`);
    await page.keyboard.press("Tab");
    await expect(role).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Tab");
    await expect(note).toBeFocused();
    await page.keyboard.type("Interested in early access.");
    await page.keyboard.press("Tab");
    await expect(page.locator("#early-access").getByRole("link", { name: "Privacy Policy" })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(submit).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(page.getByRole("status").filter({ hasText: "Thanks — your interest has been recorded." })).toBeVisible();
    await expect(page).toHaveURL(/#early-access$/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
  });

  test("shows readable field errors without saving invalid email", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 900 });
    await page.goto("/");
    await dismissCookieBanner(page);
    await page.getByLabel("Email").fill("not-an-email");
    await page.getByLabel("I am a...").selectOption("BUYER");
    await page.getByRole("button", { name: "Join early access" }).click();

    await expect(page.locator("#id_email_error")).toBeVisible();
    await expect(page.locator("#id_email")).toHaveAttribute("aria-invalid", "true");
    await expect(page.locator("#id_email")).toHaveAttribute("aria-describedby", "id_email_error");
    await expect(page.getByRole("alert").first()).toBeVisible();
  });

  test("waitlist section fits within the 1280px landing layout", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/");
    await dismissCookieBanner(page);
    const section = page.locator("#early-access");
    await expect(section).toBeVisible();
    const bounds = await section.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(1280);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1280);
  });
});
