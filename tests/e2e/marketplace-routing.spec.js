const { test, expect } = require("@playwright/test");

test.describe("marketplace route split", () => {
  test("plain root stays on the landing route", async ({ request }) => {
    const response = await request.get("/");

    expect(response.status()).toBe(200);
    expect(response.url()).toMatch(/\/$/);
    expect(await response.text()).toContain("Find manufacturers with spare capacity for small-batch orders");
  });

  test("root marketplace queries permanently redirect with the full query string", async ({ request }) => {
    const query = "q=packaging&location=Mumbai&page=2&empty=&source=a%20b";
    const response = await request.get(`/?${query}`, { maxRedirects: 0 });

    expect(response.status()).toBe(301);
    expect(response.headers().location).toBe(`/marketplace/?${query}`);
  });

  test("marketplace search runs on its dedicated route with a self canonical", async ({ page }) => {
    await page.goto("/marketplace/?q=packaging");

    await expect(page).toHaveURL(/\/marketplace\/\?q=packaging$/);
    await expect(page.getByRole("search", { name: /search manufacturing capacity/i })).toBeVisible();
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      /https:\/\/ubhaar-vyapaar\.in\/marketplace\/$/
    );
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  });
});
