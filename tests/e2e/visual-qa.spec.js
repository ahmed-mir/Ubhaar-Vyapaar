const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const widths = [320, 360, 390, 768, 1024, 1280, 1440];
const pages = [
  ["landing", "/"],
  ["marketplace", "/marketplace/"],
  ["search-results", "/marketplace/?q=packaging"],
  ["empty-results", "/marketplace/?q=__visual_qa_no_match__"],
  ["login", "/accounts/login/"],
  ["get-started", "/accounts/get-started/"],
  ["buyer-registration", "/accounts/register/"],
  ["manufacturer-registration", "/accounts/register/manufacturer/"],
  ["password-reset", "/accounts/password/reset/"],
  ["password-reset-done", "/accounts/password/reset/done/"],
  ["password-reset-confirm", "/accounts/password/reset/MQ/invalid-token/"],
  ["password-reset-complete", "/accounts/password/reset/complete/"],
  ["about", "/about/"],
  ["how-it-works", "/how-it-works/"],
  ["for-manufacturers", "/for-manufacturers/"],
  ["pricing", "/pricing-fees/"],
  ["trust-safety", "/trust-safety/"],
  ["faq", "/faq/"],
  ["contact", "/contact/"],
  ["grievance", "/grievance-redressal/"],
  ["privacy-policy", "/privacy/"],
  ["terms", "/terms/"],
  ["cookie-policy", "/cookies/"],
  ["refund-policy", "/refund-policy/"],
  ["help", "/help/"],
];

test.describe("public visual QA", () => {
  for (const width of widths) {
    test(`${width}px pages fit without broken media`, async ({ page }) => {
      test.setTimeout(240_000);
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      const output = path.join("test-results", "visual-qa", String(width));
      fs.mkdirSync(output, { recursive: true });

      await page.goto("/marketplace/");
      const reject = page.getByRole("button", { name: /reject analytics/i });
      if (await reject.isVisible()) await reject.click();

      const listingHref = await page.locator(".listing-spec-main h3 a").count()
        ? await page.locator(".listing-spec-main h3 a").first().getAttribute("href") : null;
      const profileHref = await page.locator(".listing-spec-maker a").count()
        ? await page.locator(".listing-spec-maker a").first().getAttribute("href") : null;
      const cases = [...pages];
      if (listingHref) cases.push(["listing-detail", listingHref]);
      if (profileHref) cases.push(["manufacturer-profile", profileHref]);

      const findings = [];
      for (const [name, url] of cases) {
        const response = await page.goto(url, { waitUntil: "domcontentloaded" });
        if (response.status() !== 200) {
          findings.push(`${name}: HTTP ${response.status()}`);
          continue;
        }
        await page.evaluate(async () => {
          await document.fonts.ready;
          const images = Array.from(document.images);
          images.forEach((img) => { img.loading = "eager"; });
          await Promise.race([
            Promise.all(images.map((img) => img.decode().catch(() => {}))),
            new Promise((resolve) => setTimeout(resolve, 3000))
          ]);
        });
        const issues = await page.evaluate(() => {
          const errors = [];
          if (document.documentElement.scrollWidth > innerWidth + 1) errors.push("horizontal overflow");
          const main = document.querySelector("main");
          const footer = document.querySelector("footer");
          if (main && footer && footer.getBoundingClientRect().top < main.getBoundingClientRect().bottom - 1) {
            errors.push("footer overlaps main content");
          }
          for (const img of document.images) {
            if (img.complete && !img.naturalWidth) errors.push(`broken image: ${img.getAttribute("src")}`);
            if (img.getBoundingClientRect().width > innerWidth + 1) errors.push("image wider than viewport");
          }
          for (const item of document.querySelectorAll("h1, h2, h3, .button")) {
            if (item.getBoundingClientRect().width && item.scrollWidth > item.clientWidth + 2) {
              errors.push(`clipped text: ${item.textContent.trim().slice(0, 40)}`);
            }
          }
          if (innerWidth < 768) {
            for (const control of document.querySelectorAll(
              ".marketplace-discovery input:not([type=hidden]):not([type=checkbox]):not([type=radio]), .marketplace-discovery select, .marketplace-discovery textarea"
            )) {
              if (parseFloat(getComputedStyle(control).fontSize) < 16) {
                errors.push(`marketplace control text below 16px: ${control.name}`);
              }
            }
          }
          const heading = document.querySelector("h1");
          if (!heading) errors.push("missing page heading");
          if (heading && parseFloat(getComputedStyle(heading).fontSize) > (innerWidth < 768 ? 42 : 60)) {
            errors.push("oversized page heading");
          }
          return errors;
        });
        findings.push(...issues.map((issue) => `${name}: ${issue}`));
        await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
      }

      expect(findings).toEqual([]);
    });
  }
});

test.describe("dashboard visual QA", () => {
  for (const width of widths) {
    test(`${width}px buyer and manufacturer dashboards fit`, async ({ page }) => {
      test.skip(
        !process.env.QA_BUYER_USERNAME || !process.env.QA_BUYER_PASSWORD ||
        !process.env.QA_MANUFACTURER_USERNAME || !process.env.QA_MANUFACTURER_PASSWORD,
        "Local QA account credentials are required"
      );
      test.setTimeout(120_000);
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      const output = path.join("test-results", "visual-qa", String(width));
      fs.mkdirSync(output, { recursive: true });

      for (const [role, username, password, url] of [
        ["buyer", process.env.QA_BUYER_USERNAME, process.env.QA_BUYER_PASSWORD, "/buyer/dashboard/"],
        ["manufacturer", process.env.QA_MANUFACTURER_USERNAME, process.env.QA_MANUFACTURER_PASSWORD, "/manufacturer/dashboard/"]
      ]) {
        await page.context().clearCookies();
        await page.goto("/accounts/login/");
        await page.locator('[name="username"]').fill(username);
        await page.locator('[name="password"]').fill(password);
        await page.getByRole("button", { name: /^log in$/i }).click({ noWaitAfter: true });
        await page.waitForURL((currentUrl) => !currentUrl.pathname.startsWith("/accounts/login/"), { timeout: 45_000 });
        await page.goto(url, { waitUntil: "domcontentloaded" });
        await expect(page).toHaveURL(new RegExp(`${url.replaceAll("/", "\\/")}$`));
        const reject = page.getByRole("button", { name: /reject analytics/i });
        if (await reject.isVisible()) await reject.click();
        const issues = await page.evaluate(() => {
          const errors = [];
          if (document.documentElement.scrollWidth > innerWidth + 1) errors.push("horizontal overflow");
          const main = document.querySelector("main");
          const footer = document.querySelector("footer");
          if (footer.getBoundingClientRect().top < main.getBoundingClientRect().bottom - 1) {
            errors.push("footer overlaps main content");
          }
          if (!document.querySelector("h1")) errors.push("missing page heading");
          return errors;
        });
        await page.screenshot({ path: path.join(output, `${role}-dashboard.png`), fullPage: true });
        expect(issues, `${role} dashboard at ${width}px`).toEqual([]);
      }
    });
  }
});
