const { test, expect } = require("@playwright/test");
const { dismissCookieBanner } = require("./helpers");

const password = "Cobalt-Orbit-752!";
const viewports = [320, 390, 768, 1024, 1440];

async function assertPageFits(page, width) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  const form = page.locator("form.auth-form").first();
  const box = await form.boundingBox();
  expect(box).not.toBeNull();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(width);
}

async function fillRegistration(page, { manufacturer = false, phone = "" } = {}) {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  await page.locator('[name="username"]').fill(`uv-hardening-${suffix}`);
  await page.locator('[name="email"]').fill(`uv-hardening-${suffix}@example.test`);
  await page.locator('[name="phone"]').fill(phone);
  await page.locator('[name="password1"]').fill(password);
  await page.locator('[name="password2"]').fill(password);
  if (manufacturer) {
    await page.locator('[name="business_name"]').fill(`Hardening Works ${suffix}`);
    await page.locator('[name="city"]').fill("Pune");
    await page.locator('[name="state"]').fill("Maharashtra");
  }
  await page.getByLabel(/terms.*privacy/i).check();
}

test.describe("signup and login hardening", () => {
  test.setTimeout(120000);

  test("registration and login forms remain usable from 320px through desktop", async ({ page }) => {
    for (const width of viewports) {
      await page.setViewportSize({ width, height: 900 });

      for (const route of [
        "/accounts/register/",
        "/accounts/register/manufacturer/",
        "/accounts/login/"
      ]) {
        await page.goto(route);
        await dismissCookieBanner(page);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await assertPageFits(page, width);
      }

      for (const route of ["/accounts/register/", "/accounts/register/manufacturer/"]) {
        await page.goto(route);
        const phone = page.locator('[name="phone"]');
        await expect(phone).toHaveAttribute("type", "tel");
        await expect(phone).toHaveAttribute("inputmode", "tel");
        await expect(phone).toHaveAttribute("autocomplete", "tel");

        const passwordInput = page.locator('[name="password1"]');
        const panel = page.locator("[data-password-requirements]");
        await passwordInput.focus();
        await expect(panel).toHaveJSProperty("open", true);
        await assertPageFits(page, width);
      }
    }
  });

  test("phone validation and password requirements work on both signup forms", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });

    await page.goto("/accounts/register/");
    await dismissCookieBanner(page);
    const passwordInput = page.locator('[name="password1"]');
    const requirements = page.locator("[data-password-requirements]");
    await passwordInput.focus();
    await expect(requirements).toHaveJSProperty("open", true);

    const lengthRule = requirements.locator('[data-password-rule="minimum_length"]');
    const numericRule = requirements.locator('[data-password-rule="not_numeric"]');
    const commonRule = requirements.locator('[data-password-rule="common_password"]');
    const similarityRule = requirements.locator('[data-password-rule="similarity"]');

    await passwordInput.fill("a");
    await expect(lengthRule).toHaveAttribute("data-state", "pending");
    await expect(numericRule).toHaveAttribute("data-state", "met");
    await passwordInput.fill("abcdefg");
    await expect(lengthRule).toHaveAttribute("data-state", "pending");
    await passwordInput.fill("abcdefgh");
    await expect(lengthRule).toHaveAttribute("data-state", "met");
    await expect(commonRule).toHaveAttribute("data-live-check", "false");
    await expect(similarityRule).toHaveAttribute("data-live-check", "false");
    await expect(commonRule).toContainText("Checked when you submit");
    await passwordInput.fill("12345678");
    await expect(numericRule).toHaveAttribute("data-state", "pending");
    await passwordInput.fill(password);
    await expect(lengthRule).toHaveAttribute("data-state", "met");
    await expect(numericRule).toHaveAttribute("data-state", "met");

    const confirmation = page.locator('[name="password2"]');
    const matchStatus = page.locator("[data-password-match]");
    await confirmation.fill("Different-Password-1!");
    await expect(matchStatus).toHaveAttribute("data-state", "error");
    await expect(matchStatus).toContainText("Passwords do not match");
    await confirmation.fill(password);
    await expect(matchStatus).toHaveAttribute("data-state", "met");
    await expect(matchStatus).toContainText("Passwords match");

    const passwordToggle = passwordInput.locator("xpath=following-sibling::button");
    await passwordToggle.click();
    await expect(passwordInput).toHaveAttribute("type", "text");
    await expect(passwordInput).toHaveValue(password);
    await expect(passwordToggle).toHaveAttribute("aria-pressed", "true");
    await passwordToggle.click();
    await expect(passwordInput).toHaveAttribute("type", "password");

    for (const manufacturer of [false, true]) {
      const route = manufacturer ? "/accounts/register/manufacturer/" : "/accounts/register/";
      await page.goto(route);
      await dismissCookieBanner(page);
      await fillRegistration(page, { manufacturer, phone: "dsadsaqeqewqwas" });
      await page.getByRole("button", { name: /create .* account/i }).click();
      const phoneError = page.locator("#id_phone_error");
      await expect(phoneError).toContainText(/valid phone number containing 8.?15 digits/);
      await expect(page.locator('[name="phone"]')).toHaveAttribute("aria-invalid", "true");
      expect(new URL(page.url()).pathname).toBe(route);
      await assertPageFits(page, 390);
    }
  });
});
