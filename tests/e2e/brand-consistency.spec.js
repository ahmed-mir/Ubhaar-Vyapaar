const { test, expect } = require("@playwright/test");
const {
  buildTestUser,
  registerBuyer,
  uniqueRunId,
} = require("./helpers");

async function expectCanonicalChrome(page) {
  const headerLogo = page.locator(".site-header .brand img");
  await expect(headerLogo).toHaveAttribute(
    "src",
    /\/static\/marketplace\/images\/brand\/logo\.svg$/,
  );
  await headerLogo.evaluate((image) => image.decode());

  const footerLogo = page.locator(".site-footer .footer-logo img");
  await expect(footerLogo).toHaveAttribute(
    "src",
    /\/static\/marketplace\/images\/brand\/logo-light\.svg$/,
  );
  await footerLogo.evaluate((image) => image.decode());
  await expect(page.locator('link[rel="icon"][type="image/svg+xml"]')).toHaveAttribute(
    "href",
    /\/static\/marketplace\/images\/brand\/favicon\.svg$/,
  );
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute(
    "sizes",
    "180x180",
  );
}

test("canonical logo is shared across public, auth, and authenticated chrome", async ({
  page,
}, testInfo) => {
  const screenshot = (name) => testInfo.outputPath(`${name}.png`);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expectCanonicalChrome(page);
  const faviconUrl = await page
    .locator('link[rel="icon"][type="image/svg+xml"]')
    .getAttribute("href");
  const faviconResponse = await page.request.get(new URL(faviconUrl, page.url()).href);
  expect(faviconResponse.status()).toBe(200);
  expect(await faviconResponse.text()).toContain('fill="#16241F"');
  await page.screenshot({ path: screenshot("homepage-desktop") });
  await page.locator(".site-footer").screenshot({ path: screenshot("footer") });

  await page.goto("/marketplace/");
  await expectCanonicalChrome(page);
  await page.screenshot({ path: screenshot("marketplace-desktop") });

  await page.goto("/accounts/login/");
  await expectCanonicalChrome(page);
  await page.screenshot({ path: screenshot("login") });

  const user = buildTestUser("brand", uniqueRunId());
  await registerBuyer(page, user, "LocalOnlyStrongPassword123!");
  await page.goto("/buyer/dashboard/");
  await expect(page.getByRole("heading", { name: "Dashboard", level: 1 })).toBeVisible();
  await expectCanonicalChrome(page);
  await page.screenshot({ path: screenshot("buyer-dashboard") });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expectCanonicalChrome(page);
  await expect(page.locator(".site-header .brand img")).toBeVisible();
  await page.screenshot({ path: screenshot("homepage-mobile") });
  await page.getByRole("button", { name: "Open main navigation" }).click();
  await expect(page.locator("#site-navigation")).toBeVisible();
  await page.screenshot({ path: screenshot("mobile-navigation") });
});
