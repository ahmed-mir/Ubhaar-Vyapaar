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
