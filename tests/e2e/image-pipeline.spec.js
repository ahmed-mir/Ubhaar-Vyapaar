const { test, expect } = require("@playwright/test");

const viewports = [320, 390, 768, 1024, 1440];

async function expectImagesLoaded(page, selector) {
  const images = page.locator(selector);
  await expect(images.first()).toBeVisible();
  const results = [];
  const count = Math.min(await images.count(), 3);
  for (let index = 0; index < count; index += 1) {
    const image = images.nth(index);
    await image.scrollIntoViewIfNeeded();
    await image.evaluate((element) => element.decode());
    results.push(await image.evaluate((element) => ({
      naturalWidth: element.naturalWidth,
      src: element.currentSrc,
      loading: element.loading,
      decoding: element.decoding,
      width: element.getAttribute("width"),
      height: element.getAttribute("height"),
      srcset: element.getAttribute("srcset"),
      sizes: element.getAttribute("sizes")
    })));
  }

  for (const image of results) {
    expect(image.naturalWidth).toBeGreaterThan(0);
    expect(image.decoding).toBe("async");
    expect(image.width).toBeTruthy();
    expect(image.height).toBeTruthy();
    expect(image.loading).toBe("lazy");
  }
  return results;
}

test.describe("responsive listing image delivery", () => {
  test("marketplace images reserve space and load at supported viewports", async ({ page }) => {
    for (const width of viewports) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/marketplace/");
      const images = await expectImagesLoaded(page, ".listing-image");
      for (const image of images) {
        if (image.src.startsWith("https://res.cloudinary.com/")) {
          expect(image.srcset).toBeTruthy();
          expect(image.sizes).toBeTruthy();
        }
      }
    }
  });

  test("listing detail image is eager, high priority, and stable across viewports", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/marketplace/");
    const listingHref = await page.locator(".listing-spec-main h3 a").first().getAttribute("href");
    expect(listingHref).toBeTruthy();

    for (const width of viewports) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(listingHref);
      const image = page.locator("img.detail-image");
      await expect(image).toBeVisible();
      await image.evaluate((element) => element.decode());
      const result = await image.evaluate((element) => ({
        naturalWidth: element.naturalWidth,
        src: element.currentSrc,
        loading: element.loading,
        fetchpriority: element.getAttribute("fetchpriority"),
        decoding: element.decoding,
        width: element.getAttribute("width"),
        height: element.getAttribute("height"),
        srcset: element.getAttribute("srcset"),
        sizes: element.getAttribute("sizes")
      }));
      expect(result.naturalWidth).toBeGreaterThan(0);
      expect(result.loading).toBe("eager");
      expect(result.fetchpriority).toBe("high");
      expect(result.decoding).toBe("async");
      expect(result.width).toBe("800");
      expect(result.height).toBe("600");
      if (result.src.startsWith("https://res.cloudinary.com/")) {
        expect(result.srcset).toBeTruthy();
        expect(result.sizes).toBeTruthy();
      }
    }
  });
});
