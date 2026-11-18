const { test, expect } = require("@playwright/test");
const { dismissCookieBanner } = require("./helpers");

const password = "Strong@4821";
const viewports = [320, 390, 768, 1024, 1440];

async function assertPageFits(page, width) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  const form = page.locator("form.auth-form").first();
  const box = await form.boundingBox();
  expect(box).not.toBeNull();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(width);
}

async function fillRegistration(page, { manufacturer = false, email, username } = {}) {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  await page.locator('[name="username"]').fill(username || `uv-hardening-${suffix}`);
  await page.locator('[name="email"]').fill(email || `uv-hardening-${suffix}@example.test`);
  await page.locator('[name="phone"]').fill("9876543210");
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

  test("auth forms remain usable at 320px through desktop widths", async ({ page }) => {
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
        await expect(phone).toHaveAttribute("inputmode", "numeric");
        await expect(phone).toHaveAttribute("autocomplete", "tel-national");
        await expect(phone).toHaveAttribute("maxlength", "10");
        await expect(phone).toHaveAttribute("pattern", "[0-9]{10}");
        await expect(page.locator(".phone-country-prefix")).toHaveText("+91");

        const requirements = page.locator("[data-password-requirements]");
        await expect(requirements).toBeVisible();
        await expect(requirements.locator("[data-password-rule]")).toHaveCount(4);
        await expect(requirements).not.toContainText("too common");
        await assertPageFits(page, width);
      }

      await page.goto("/accounts/login/");
      await expect(page.getByLabel("Email or username")).toHaveAttribute("autocomplete", "username");
      const loginPassword = page.locator('[name="password"]');
      await expect(loginPassword).toHaveAttribute("autocomplete", "current-password");
      await expect(page.locator("[data-password-requirements]")).toHaveCount(0);
      await loginPassword.fill("ExistingPassword123!");
      const toggle = loginPassword.locator("xpath=following-sibling::button");
      await toggle.focus();
      await page.keyboard.press("Enter");
      await expect(loginPassword).toHaveAttribute("type", "text");
      await expect(toggle).toHaveAttribute("aria-pressed", "true");
      await assertPageFits(page, width);
    }
  });

  test("India phone input and password checklist update live", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });

    for (const route of ["/accounts/register/", "/accounts/register/manufacturer/"]) {
      await page.goto(route);
      await dismissCookieBanner(page);
      const phone = page.locator('[name="phone"]');
      await expect(page.locator(".phone-country-prefix")).toBeVisible();
      await phone.fill("abcdefghij");
      await expect(phone).toHaveValue("");
      await phone.fill("98765abc12");
      await expect(phone).toHaveValue(/^[0-9]{0,10}$/);
      await phone.fill("1234567890");
      await phone.press("End");
      await phone.pressSequentially("1");
      await expect(phone).toHaveValue("1234567890");

      const username = page.locator('[name="username"]');
      const email = page.locator('[name="email"]');
      await username.fill("different-user");
      await email.fill("unrelated@example.test");

      const requirements = page.locator("[data-password-requirements]");
      await expect(requirements).toBeVisible();
      const length = requirements.locator('[data-password-rule="minimum_length"]');
      const symbol = requirements.locator('[data-password-rule="symbol"]');
      const numeric = requirements.locator('[data-password-rule="not_numeric"]');
      const similarity = requirements.locator('[data-password-rule="similarity"]');
      const passwordInput = page.locator('[name="password1"]');

      await passwordInput.fill("abcdefgh");
      await expect(length).toHaveAttribute("data-state", "met");
      await expect(symbol).toHaveAttribute("data-state", "pending");
      await expect(numeric).toHaveAttribute("data-state", "met");
      await expect(similarity).toHaveAttribute("data-state", "met");

      await username.fill("abcdefgh");
      await expect(similarity).toHaveAttribute("data-state", "error");
      await username.fill("different-user");
      await expect(similarity).toHaveAttribute("data-state", "met");

      await passwordInput.fill("abcdefgh@");
      await expect(symbol).toHaveAttribute("data-state", "met");

      await email.fill("Ahmed@example.test");
      await passwordInput.fill("Ahmed@example.test");
      await expect(similarity).toHaveAttribute("data-state", "error");
      await email.fill("other@acme.com");
      await expect(similarity).toHaveAttribute("data-state", "met");

      const confirmation = page.locator('[name="password2"]');
      const matchStatus = page.locator("[data-password-match]");
      await confirmation.fill("Different@123");
      await expect(matchStatus).toHaveAttribute("data-state", "error");
      await confirmation.fill("Ahmed@example.test");
      await expect(matchStatus).toHaveAttribute("data-state", "met");
      await assertPageFits(page, 390);
    }
  });

  test("Buyer and Manufacturer reject case-insensitive duplicate emails", async ({ page, browser }) => {
    await page.goto("/accounts/register/");
    await dismissCookieBanner(page);
    const email = `case-check-${Date.now()}@example.test`;
    await fillRegistration(page, { email, username: `buyer-${Date.now()}` });
    await page.getByRole("button", { name: "Create buyer account" }).click();
    await expect(page).toHaveURL(/\/$/);

    const secondContext = await browser.newContext();
    const manufacturerPage = await secondContext.newPage();
    await manufacturerPage.goto("/accounts/register/manufacturer/");
    await dismissCookieBanner(manufacturerPage);
    await fillRegistration(manufacturerPage, {
      manufacturer: true,
      email: email.toUpperCase(),
      username: `manufacturer-${Date.now()}`
    });
    await manufacturerPage.getByRole("button", { name: "Create manufacturer account" }).click();
    await expect(manufacturerPage.locator("#id_email_error")).toContainText(
      "An account with this email address already exists."
    );
    await expect(manufacturerPage).toHaveURL(/register\/manufacturer\/$/);
    await secondContext.close();
  });
});
