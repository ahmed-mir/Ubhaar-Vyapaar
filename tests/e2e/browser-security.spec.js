const { test, expect } = require("@playwright/test");

test.describe("browser security policy", () => {
  test("nonce CSP preserves navigation, filters, FAQ, and login without violations", async ({ page }) => {
    const violations = [];
    page.on("console", (message) => {
      if (/content security policy/i.test(message.text())) {
        violations.push(message.text());
      }
    });
    await page.addInitScript(() => {
      window.__cspViolations = [];
      window.addEventListener("securitypolicyviolation", (event) => {
        window.__cspViolations.push({
          directive: event.violatedDirective,
          blockedURI: event.blockedURI
        });
      });
    });

    const marketplace = await page.goto("/marketplace/");
    expect(marketplace.status()).toBe(200);
    await expect(page.getByRole("heading", { name: /browse manufacturing capacity/i })).toBeVisible();
    const filterDisclosure = page.locator(".marketplace-filter-disclosure");
    await expect(filterDisclosure).toHaveAttribute("open", "");

    const faq = await page.goto("/faq/");
    expect(faq.status()).toBe(200);
    const firstQuestion = page.locator(".public-faq-list summary").first();
    await firstQuestion.click();
    await expect(firstQuestion.locator("xpath=.." )).toHaveAttribute("open", "");
    await firstQuestion.click();
    await expect(firstQuestion.locator("xpath=.." )).not.toHaveAttribute("open", "");

    const login = await page.goto("/accounts/login/");
    expect(login.status()).toBe(200);
    await expect(page.locator('input[name="username"]')).toBeVisible();

    expect(await page.evaluate(() => window.__cspViolations)).toEqual([]);
    expect(violations).toEqual([]);
  });
});
