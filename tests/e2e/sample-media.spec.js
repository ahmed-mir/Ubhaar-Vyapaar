const { test, expect } = require("@playwright/test");

test.describe("Sample listing media", () => {
  for (const width of [390, 1440]) {
    test(`uses loaded first-party images at ${width}px`, async ({ page }) => {
      const brokenSampleRequests = [];
      const failedFirstPartyImages = [];
      const pageErrors = [];
      const sampleMediaConsoleErrors = [];

      page.on("request", (request) => {
        if (/res\.cloudinary\.com\/.*demo\/listings\//i.test(request.url())) {
          brokenSampleRequests.push(request.url());
        }
      });
      page.on("response", (response) => {
        if (
          response.url().includes("/static/marketplace/images/demo/") &&
          response.status() >= 400
        ) {
          failedFirstPartyImages.push(`${response.status()} ${response.url()}`);
        }
      });
      page.on("pageerror", (error) => pageErrors.push(error.message));
      page.on("console", (message) => {
        if (
          message.type() === "error" &&
          /cloudinary|demo\/listings|marketplace\/images\/demo/i.test(message.text())
        ) {
          sampleMediaConsoleErrors.push(message.text());
        }
      });
      page.on("requestfailed", (request) => {
        if (/marketplace\/images\/demo|demo\/listings/i.test(request.url())) {
          sampleMediaConsoleErrors.push(`${request.url()}: ${request.failure()?.errorText}`);
        }
      });
      await page.setViewportSize({ width, height: 900 });

      await page.goto("/");
      const homeSampleImage = page
        .locator('[data-sample-listing="true"] img[src*="/static/marketplace/images/demo/"]')
        .first();
      await expect(homeSampleImage).toBeVisible();
      await expect.poll(() => homeSampleImage.evaluate((image) => image.naturalWidth)).toBeGreaterThan(0);

      await page.goto("/marketplace/");
      const sampleCard = page.locator('[data-sample-listing="true"]').first();
      await expect(sampleCard).toBeVisible();
      const sampleCardImage = sampleCard.locator('img[src*="/static/marketplace/images/demo/"]');
      await expect(sampleCardImage).toBeVisible();
      await expect.poll(() => sampleCardImage.evaluate((image) => image.naturalWidth)).toBeGreaterThan(0);
      const detailHref = await sampleCard.locator('a[href^="/listings/"]').first().getAttribute("href");

      await page.goto(detailHref);
      await expect(page.locator(".sample-badge").first()).toBeVisible();
      const detailImage = page.locator(".detail-image[src*='/static/marketplace/images/demo/']");
      await expect.poll(() => detailImage.evaluate((image) => image.naturalWidth)).toBeGreaterThan(0);
      await expect(page.getByRole("link", { name: "Request a quote" })).toHaveCount(0);

      const imageFrame = page.locator(".listing-sheet-media");
      const box = await imageFrame.boundingBox();
      expect(box.width).toBeGreaterThan(0);
      expect(box.height).toBeGreaterThan(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      expect(brokenSampleRequests).toEqual([]);
      expect(failedFirstPartyImages).toEqual([]);
      expect(sampleMediaConsoleErrors).toEqual([]);
      expect(pageErrors).toEqual([]);
    });
  }
});
