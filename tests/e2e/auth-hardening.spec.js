const { test, expect } = require("@playwright/test");
const { dismissCookieBanner } = require("./helpers");
const fs = require("node:fs");
const path = require("node:path");

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
    await page.locator('[name="state"]').selectOption("Maharashtra");
    await page.locator('[name="pincode"]').fill("400001");
  }
  await page.getByLabel(/terms.*privacy/i).check();
}

test.describe("signup and login hardening", () => {
  test.setTimeout(120000);

  test("auth forms remain usable at 320px through desktop widths", async ({ page }) => {
    const registrationRoutes = [
      "/accounts/register/",
      "/accounts/register/manufacturer/"
    ];
    const screenshotDir = path.join(process.cwd(), "phase8g-screenshots");
    fs.mkdirSync(screenshotDir, { recursive: true });

    for (const route of [...registrationRoutes, "/accounts/login/"]) {
      const pageName = route.endsWith("manufacturer/")
        ? "manufacturer-registration"
        : route.endsWith("register/") ? "buyer-registration" : "login";
      await page.goto(route);
      await dismissCookieBanner(page);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

      for (const width of viewports) {
        await page.setViewportSize({ width, height: 900 });
        await assertPageFits(page, width);

        if (registrationRoutes.includes(route)) {
          await expect(page.locator(".auth-required-note")).toContainText("unless marked Optional");
          await expect(page.locator(".account-field-optionality").first()).toHaveText("Optional");
          await expect(page.locator(".auth-flow-switch a")).toBeVisible();
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
        } else {
          const username = page.getByLabel("Email or username");
          await expect(page.locator("#id_username_helptext")).toContainText("Phone sign-in is not available");
          await expect(username).toHaveAttribute("autocomplete", "username");
          const loginPassword = page.locator('[name="password"]');
          await expect(loginPassword).toHaveAttribute("autocomplete", "current-password");
          await expect(page.locator("[data-password-requirements]")).toHaveCount(0);

          if (width === viewports[0]) {
            await loginPassword.fill("ExistingPassword123!");
            const toggle = loginPassword.locator("xpath=following-sibling::button");
            const toggleBox = await toggle.boundingBox();
            expect(toggleBox.width).toBeGreaterThanOrEqual(44);
            expect(toggleBox.height).toBeGreaterThanOrEqual(44);
            await toggle.focus();
            await page.keyboard.press("Enter");
            await expect(loginPassword).toHaveAttribute("type", "text");
            await expect(toggle).toHaveAttribute("aria-pressed", "true");
            await toggle.click();
          }
        }

        await assertPageFits(page, width);
        await page.screenshot({
          path: path.join(screenshotDir, `${pageName}-${width}.png`),
          fullPage: true
        });
      }
    }

    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto("/accounts/register/");
    await dismissCookieBanner(page);
    await page.locator('[name="username"]').fill("phase8g-screenshot-buyer");
    await page.locator('[name="email"]').fill("phase8g-screenshot@example.test");
    await page.locator('[name="password1"]').fill(password);
    await page.screenshot({
      path: path.join(screenshotDir, "password-requirements-390.png"),
      fullPage: true
    });

    for (const [route, name] of [
      ["/accounts/register/", "buyer"],
      ["/accounts/register/manufacturer/", "manufacturer"]
    ]) {
      await page.goto(route);
      await dismissCookieBanner(page);
      await page.setViewportSize({ width: 390, height: 900 });
      await page.getByRole("button", { name: /Create .*account/ }).click();
      await expect(page.locator(".form-error-summary")).toBeVisible();
      await page.screenshot({
        path: path.join(screenshotDir, `${name}-validation-390.png`),
        fullPage: true
      });
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

  test("Manufacturer location uses one State/UT dropdown and validates PIN at 320px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await page.goto("/accounts/register/manufacturer/");
    await dismissCookieBanner(page);

    const state = page.locator('[name="state"]');
    const pincode = page.locator('[name="pincode"]');
    await expect(state).toHaveCount(1);
    await expect(page.locator('[name="union_territory"]')).toHaveCount(0);
    await expect(state.locator("option")).toHaveCount(37);
    await expect(state.locator("option").first()).toHaveText("Select State / Union Territory");
    for (const value of ["Maharashtra", "Delhi", "Puducherry"]) {
      await state.selectOption(value);
      await expect(state).toHaveValue(value);
    }

    await expect(pincode).toHaveAttribute("type", "text");
    await expect(pincode).toHaveAttribute("inputmode", "numeric");
    await expect(pincode).toHaveAttribute("maxlength", "6");
    await expect(pincode).toHaveAttribute("autocomplete", "postal-code");
    await expect(pincode).toHaveAttribute("pattern", "[1-9][0-9]{5}");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);

    await fillRegistration(page, { manufacturer: true });
    await pincode.fill("000001");
    await page.getByRole("button", { name: "Create manufacturer account" }).click();
    await expect(page.locator("#id_pincode_error")).toContainText(
      "Enter a valid 6-digit Indian PIN code."
    );
    await expect(page).toHaveURL(/register\/manufacturer\/$/);

    await fillRegistration(page, { manufacturer: true });
    await pincode.fill("560001");
    await page.getByRole("button", { name: "Create manufacturer account" }).click();
    await expect(page).toHaveURL(/manufacturer\/dashboard\/$/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  });
});
