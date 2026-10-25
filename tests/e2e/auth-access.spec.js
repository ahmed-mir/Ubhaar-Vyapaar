const { test, expect } = require("@playwright/test");
const {
  buildTestUser,
  createListing,
  login,
  logout,
  registerBuyer,
  registerManufacturer,
  requireEnv,
  uniqueRunId
} = require("./helpers");

test.describe("production auth and access smoke", () => {
  test.setTimeout(120000);

  test("local login accepts username or email and rejects wrong credentials", async ({ page }) => {
    test.setTimeout(240000);
    test.skip(
      Boolean(process.env.UBHAAR_BASE_URL),
      "This login flow creates a disposable account and runs only on the local Playwright server."
    );
    const password = "StrongPass123!";
    const buyer = buildTestUser("email-login", uniqueRunId());
    await registerBuyer(page, buyer, password);
    await logout(page);

    await page.setViewportSize({ width: 360, height: 850 });
    await login(page, buyer.username, password);
    await page.goto("/buyer/dashboard/");
    await expect(page.getByRole("heading", { name: /what needs attention/i })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);

    await page.setViewportSize({ width: 1280, height: 900 });
    await logout(page);
    await login(page, buyer.email.toUpperCase(), password);
    await page.goto("/buyer/dashboard/");
    await expect(page.getByRole("heading", { name: /what needs attention/i })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1280);
    await logout(page);

    await page.setViewportSize({ width: 360, height: 850 });
    await page.goto("/accounts/login/");
    await page.locator('[name="username"]').fill(`uv-e2e-unknown-${uniqueRunId()}`);
    await page.locator('[name="password"]').fill("WrongPassword123!");
    const invalidLoginResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith("/accounts/login/") &&
        response.request().method() === "POST",
      { timeout: 90000 }
    );
    await page.getByRole("button", { name: /^log in$/i }).click({ noWaitAfter: true });
    const response = await invalidLoginResponse;
    expect(response.status()).toBe(200);
    await expect(
      page.getByText("Please enter a correct email or username and password.")
    ).toBeVisible({ timeout: 60000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
  });

  test("role chooser and password controls work at mobile and desktop widths", async ({ page }) => {
    for (const width of [360, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/accounts/get-started/");

      await expect(page.getByRole("heading", { name: /choose your account type/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /continue as buyer/i })).toHaveAttribute(
        "href",
        "/accounts/register/"
      );
      await expect(page.getByRole("link", { name: /continue as manufacturer/i })).toHaveAttribute(
        "href",
        "/accounts/register/manufacturer/"
      );
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);

      const buyerLink = page.getByRole("link", { name: /continue as buyer/i });
      await buyerLink.focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/\/accounts\/register\/$/);

      await expect(page.getByLabel("Username")).toBeVisible();
      await expect(page.getByLabel(/terms.*privacy/i)).toBeVisible();
      const consent = page.getByLabel(/terms.*privacy/i);
      await consent.check();
      await expect(consent).toBeChecked();

      const password = page.locator('[name="password1"]');
      await password.fill("StrongPass123!");
      const show = page.getByRole("button", { name: "Show password" }).first();
      await show.focus();
      await page.keyboard.press("Enter");
      await expect(password).toHaveAttribute("type", "text");
      await expect(page.getByRole("button", { name: "Hide password" }).first()).toHaveAttribute(
        "aria-pressed",
        "true"
      );
      await expect(password).toHaveValue("StrongPass123!");
      await page.keyboard.press("Enter");
      await expect(password).toHaveAttribute("type", "password");
      await expect(password).toHaveValue("StrongPass123!");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);

      await page.goto("/accounts/register/manufacturer/");
      await expect(page.getByLabel("Username")).toBeVisible();
      await expect(page.getByLabel("Business name")).toBeVisible();
      await expect(page.locator('[name="city"]')).toBeVisible();
      await expect(page.locator('[name="state"]')).toBeVisible();
      await expect(page.getByLabel(/terms.*privacy/i)).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);

      await page.goto("/accounts/login/");
      await expect(page.getByLabel("Email or username")).toBeVisible();
      const loginPassword = page.locator('[name="password"]');
      await loginPassword.fill("ExistingPassword123!");
      await page.getByRole("button", { name: "Show password" }).focus();
      await page.keyboard.press("Enter");
      await expect(loginPassword).toHaveAttribute("type", "text");
      await expect(loginPassword).toHaveValue("ExistingPassword123!");
      await expect(page.getByRole("button", { name: "Hide password" })).toHaveAttribute(
        "aria-pressed",
        "true"
      );
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    }
  });

  test("buyer registration, dashboard, login, and logout", async ({ page }) => {
    test.skip(!process.env.TEST_USER_PASSWORD, "TEST_USER_PASSWORD is required for QA account flows");
    const password = requireEnv("TEST_USER_PASSWORD");
    const buyer = buildTestUser("buyer", uniqueRunId());

    await registerBuyer(page, buyer, password);

    await page.locator('a[href="/buyer/dashboard/"]').first().click();
    await expect(page).toHaveURL(/\/buyer\/dashboard\/$/);
    await expect(page.getByRole("heading", { name: /what needs attention/i })).toBeVisible();

    await logout(page);
    await login(page, buyer.username, password);
    await expect(page.locator('a[href="/buyer/dashboard/"]').first()).toBeVisible();
    await logout(page);
  });

  test("manufacturer registration, dashboard, login, logout, and listing creation", async ({ page }) => {
    test.skip(!process.env.TEST_USER_PASSWORD, "TEST_USER_PASSWORD is required for QA account flows");
    const password = requireEnv("TEST_USER_PASSWORD");
    const runId = uniqueRunId();
    const manufacturer = buildTestUser("manufacturer", runId);
    const listingTitle = `UV E2E Unverified Capacity ${runId}`;

    await registerManufacturer(page, manufacturer, password, {
      businessName: `UV E2E Works ${runId}`,
      description: "Disposable manufacturer profile created by production smoke tests.",
      city: "Pune",
      state: "Maharashtra"
    });

    await createListing(page, {
      title: listingTitle,
      category: "PACKAGING",
      description: "Disposable smoke-test listing for package assembly capacity.",
      machineType: "Semi automatic packing line",
      materials: "Kraft paper, corrugated board",
      capabilities: "Short-run packaging assembly and labeling.",
      minimumQuantity: 25,
      pricePerUnit: "12.50",
      batchPrice: "300.00",
      productionDays: 4,
      availableCapacity: 500,
      capacityPeriod: "per week",
      cluster: "Pune industrial area"
    });

    await page.goto("/manufacturer/listings/");
    await expect(page.getByRole("heading", { name: listingTitle })).toBeVisible();
    await expect(page.getByText(/awaiting verification/i)).toBeVisible();

    await logout(page);
    await login(page, manufacturer.username, password);
    await expect(page.getByRole("link", { name: /^Dashboard$/i })).toBeVisible();
    await logout(page);
  });

  test("role-based access restrictions", async ({ page }) => {
    test.skip(!process.env.TEST_USER_PASSWORD, "TEST_USER_PASSWORD is required for QA account flows");
    const password = requireEnv("TEST_USER_PASSWORD");
    const runId = uniqueRunId();
    const buyer = buildTestUser("buyer-access", runId);
    const manufacturer = buildTestUser("manufacturer-access", runId);

    await page.goto("/buyer/dashboard/");
    await expect(page).toHaveURL(/\/accounts\/login\/\?next=\/buyer\/dashboard\//);

    await registerBuyer(page, buyer, password);
    const manufacturerDashboardResponse = await page.goto("/manufacturer/dashboard/");
    expect(manufacturerDashboardResponse.status()).toBe(403);
    await page.goto("/");
    await logout(page);

    await registerManufacturer(page, manufacturer, password, {
      businessName: `UV E2E Access Works ${runId}`,
      description: "Disposable access restriction manufacturer profile.",
      city: "Surat",
      state: "Gujarat"
    });
    const buyerDashboardResponse = await page.goto("/buyer/dashboard/");
    expect(buyerDashboardResponse.status()).toBe(403);
    await page.goto("/");
    await logout(page);
  });

  test("password reset page accepts a reset request", async ({ page }) => {
    const runId = uniqueRunId();

    await page.goto("/accounts/password/reset/");
    await page.locator('[name="email"]').fill(`uv-e2e-reset-${runId}@example.com`);
    await page.getByRole("button", { name: /send reset link/i }).click();

    await expect(page).toHaveURL(/\/accounts\/password\/reset\/done\/$/);
    await expect(page.getByRole("heading", { name: /check your email/i })).toBeVisible();
  });
});
