const { test, expect } = require("@playwright/test");

test.describe("shared micro-interactions", () => {
  test("desktop navbar hover stays distinct from the current page without moving links", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/marketplace/");
    await page.evaluate(() => document.fonts.ready);

    const navigation = page.getByRole("navigation", { name: "Main navigation" });
    const activeMarketplace = navigation.getByRole("link", { name: "Marketplace", exact: true });
    await expect(activeMarketplace).toHaveAttribute("aria-current", "page");
    const links = [
      activeMarketplace,
      navigation.getByRole("link", { name: "How it works", exact: true }),
      navigation.getByRole("link", { name: "For manufacturers", exact: true }),
      page.locator("#site-navigation .nav-menu > summary", { hasText: "Resources" })
    ];

    const geometry = async (locator) =>
      locator.evaluate((element) => {
        const { x, y, width, height } = element.getBoundingClientRect();
        return { x, y, width, height };
      });
    const initial = await Promise.all(links.map(geometry));

    for (const link of links) {
      await link.hover();
      await page.evaluate(
        () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
      );
      expect(await Promise.all(links.map(geometry))).toEqual(initial);
      await expect(activeMarketplace).toHaveAttribute("aria-current", "page");
    }

    const activeBackground = await activeMarketplace.evaluate(
      (element) => getComputedStyle(element).backgroundColor
    );
    await navigation.getByRole("link", { name: "How it works", exact: true }).hover();
    expect(
      await activeMarketplace.evaluate((element) => getComputedStyle(element).backgroundColor)
    ).toBe(activeBackground);

    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 850 });
      await page.goto("/");
      const toggle = page.locator(".nav-toggle");
      await toggle.click();
      const mobileNavigation = page.getByRole("navigation", { name: "Main navigation" });
      await expect(mobileNavigation.getByRole("link", { name: "Marketplace", exact: true })).toBeVisible();
      const resources = mobileNavigation.locator(".nav-menu > summary", { hasText: "Resources" });
      await resources.click();
      await expect(resources.locator("xpath=.." )).toHaveAttribute("open", "");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    }
  });

  test("FAQ answers expand and collapse in normal flow, including rapid toggles", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 850 });
    await page.goto("/");

    const items = page.locator(".landing-faq-list details");
    await expect(items).toHaveCount(6);
    const first = items.nth(0);
    const second = items.nth(1);
    const firstSummary = first.locator(":scope > summary");
    const firstAnswer = first.locator(":scope > .faq-answer-motion");
    const footer = page.locator("footer");
    await expect(first).not.toHaveAttribute("open", "");
    await expect(firstAnswer).toBeHidden();
    await firstSummary.scrollIntoViewIfNeeded();
    const originalScrollY = await page.evaluate(() => window.scrollY);
    const originalFooterTop = await footer.evaluate(
      (element) => element.getBoundingClientRect().top + window.scrollY
    );

    await firstAnswer.evaluate((element) => {
      window.__faqMotionTransitions = [];
      element.addEventListener("transitionrun", (event) => {
        window.__faqMotionTransitions.push(event.propertyName);
      });
    });
    await firstSummary.click();
    await expect(first).toHaveAttribute("open", "");
    await expect(firstAnswer).toBeVisible();
    await expect.poll(() => page.evaluate(() => window.__faqMotionTransitions)).toContain("height");
    await expect(first).not.toHaveAttribute("data-faq-animating", "");
    const expandedFooterTop = await footer.evaluate(
      (element) => element.getBoundingClientRect().top + window.scrollY
    );
    expect(expandedFooterTop).toBeGreaterThan(originalFooterTop);
    expect(await page.evaluate(() => window.scrollY)).toBe(originalScrollY);

    await second.locator(":scope > summary").click();
    await expect(second).toHaveAttribute("open", "");
    await expect(first).toHaveAttribute("open", "");
    await second.locator(":scope > summary").click();
    await expect(second).not.toHaveAttribute("open", "");

    await firstSummary.click();
    await expect(first).not.toHaveAttribute("open", "");
    await expect(first).not.toHaveAttribute("data-faq-animating", "");
    await expect(firstAnswer).toBeHidden();
    await expect.poll(() => footer.evaluate(
      (element) => element.getBoundingClientRect().top + window.scrollY
    )).toBe(originalFooterTop);
    expect(await firstAnswer.getAttribute("style")).toBe("");

    await firstSummary.evaluate((element) => {
      element.click();
      element.click();
      element.click();
    });
    await expect(first).toHaveAttribute("open", "");
    await expect(first).not.toHaveAttribute("data-faq-animating", "");
    await firstSummary.click();
    await expect(first).not.toHaveAttribute("open", "");

    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 850 });
      await expect(firstSummary).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await firstSummary.click();
      await expect(first).toHaveAttribute("open", "");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await firstSummary.click();
      await expect(first).not.toHaveAttribute("open", "");
    }
  });

  test("FAQ disclosures remain keyboard-operable with reduced motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: 390, height: 850 });
    await page.goto("/faq/");

    const details = page.locator(".public-faq-list details").first();
    const summary = details.locator(":scope > summary");
    await expect(details).not.toHaveAttribute("open", "");
    await summary.focus();
    await page.keyboard.press("Space");
    await expect(details).toHaveAttribute("open", "");
    await expect(details).not.toHaveAttribute("data-faq-animating", "");
    await expect(details.locator(":scope > .faq-answer-motion")).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(details).not.toHaveAttribute("open", "");
    await expect(details).not.toHaveAttribute("data-faq-animating", "");

    const browseButton = page.getByRole("link", { name: "Browse marketplace" });
    await browseButton.hover();
    expect(await browseButton.evaluate((element) => getComputedStyle(element).transform)).toBe("none");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});
