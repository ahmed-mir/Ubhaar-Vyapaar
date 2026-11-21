const { test, expect } = require("@playwright/test");

test.describe("accessibility and keyboard UX", () => {
  test("mobile navigation opens, closes, and returns focus with keyboard", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto("/");

    const toggle = page.locator(".nav-toggle");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAccessibleName(/open main navigation/i);
    const toggleBox = await toggle.boundingBox();
    expect(toggleBox.height).toBeGreaterThanOrEqual(44);
    expect(toggleBox.width).toBeGreaterThanOrEqual(44);
    await toggle.focus();
    await page.keyboard.press("Enter");

    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(toggle).toHaveAccessibleName(/close main navigation/i);
    await expect(page.getByRole("navigation", { name: /main navigation/i })).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(toggle).toHaveAccessibleName(/open main navigation/i);
    await expect(toggle).toBeFocused();
  });

  test("registration errors are associated with invalid fields", async ({ page }) => {
    await page.goto("/accounts/register/");
    await page.getByRole("button", { name: /create buyer account/i }).click();

    const username = page.locator("[name='username']");
    await expect(username).toHaveAttribute("aria-invalid", "true");
    await expect(username).toHaveAttribute("aria-describedby", /id_username_error/);
    await expect(page.locator("#id_username_error")).toHaveCount(1);
    await expect(page.locator("#id_username_error")).toBeVisible();
  });

  test("skip link moves keyboard users to main content", async ({ page }) => {
    await page.goto("/");

    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: /skip to main content/i })).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(page.locator("#main-content")).toBeFocused();
  });

  test("cookie preferences dialog is named and Escape returns focus", async ({ page }) => {
    await page.goto("/");

    const banner = page.locator("[data-cookie-consent]");
    const rejectCookies = page.getByRole("button", { name: /reject analytics/i });
    if (await rejectCookies.isVisible()) await rejectCookies.click();

    const settings = page.getByRole("button", { name: /cookie settings/i });
    await settings.focus();
    await page.keyboard.press("Enter");

    const dialog = page.getByRole("dialog", { name: "Cookie choices" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute("aria-modal", "false");
    await page.keyboard.press("Escape");

    await expect(banner).toBeHidden();
    await expect(settings).toBeFocused();
  });

  test("page landmarks and authentication controls have accessible names", async ({ page }) => {
    await page.goto("/accounts/login/");

    await expect(page.locator("main")).toHaveCount(1);
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    await expect(page.getByLabel(/email or username/i)).toBeVisible();
    await expect(page.getByLabel(/^password:?$/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /show password/i })).toBeVisible();
  });

  test("public and login pages expose one main landmark and one primary heading", async ({ page }) => {
    for (const path of ["/", "/marketplace/", "/about/", "/faq/", "/contact/", "/accounts/login/"]) {
      await page.goto(path);
      await expect(page.locator("main")).toHaveCount(1, { timeout: 15000 });
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1, { timeout: 15000 });
      const levels = await page.locator("h1, h2, h3, h4, h5, h6").evaluateAll((headings) =>
        headings.filter((heading) => heading.getClientRects().length)
          .map((heading) => Number(heading.tagName.slice(1)))
      );
      for (let index = 1; index < levels.length; index += 1) {
        expect(levels[index], `${path} heading order`).toBeLessThanOrEqual(levels[index - 1] + 1);
      }
    }
  });

  test("representative pages reflow at a 200-percent-equivalent 640px viewport", async ({ page }) => {
    await page.setViewportSize({ width: 640, height: 900 });
    for (const path of ["/", "/marketplace/", "/accounts/login/", "/accounts/register/", "/accounts/register/manufacturer/", "/contact/"]) {
      await page.goto(path);
      const dimensions = await page.evaluate(() => ({
        viewport: window.innerWidth,
        document: document.documentElement.scrollWidth
      }));
      expect(dimensions.document, `${path} at 640 CSS px`).toBeLessThanOrEqual(dimensions.viewport + 1);
    }
  });

  test("key text and focus colors meet contrast targets", async ({ page }) => {
    await page.goto("/");
    const results = await page.evaluate(() => {
      const parse = (value) => {
        const hex = value.trim().match(/^#([\da-f]{3}|[\da-f]{6})$/i);
        if (hex) {
          const expanded = hex[1].length === 3 ? hex[1].split("").map((part) => part + part).join("") : hex[1];
          return { rgb: [0, 2, 4].map((index) => Number.parseInt(expanded.slice(index, index + 2), 16)), alpha: 1 };
        }
        const match = value.match(/rgba?\(([^)]+)\)/);
        if (!match) return null;
        const channels = match[1].split(",").map((channel) => Number.parseFloat(channel.trim()));
        return { rgb: channels.slice(0, 3), alpha: channels.length === 4 ? channels[3] : 1 };
      };
      const luminance = (rgb) => {
        const channels = rgb.map((channel) => {
          const value = channel / 255;
          return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
        });
        return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
      };
      const ratio = (foreground, background) => {
        const first = luminance(foreground);
        const second = luminance(background);
        return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
      };
      const backgroundFor = (element) => {
        for (let current = element; current; current = current.parentElement) {
          const color = parse(getComputedStyle(current).backgroundColor);
          if (color && color.alpha > 0.99) return color.rgb;
        }
        return [255, 255, 255];
      };
      const pairs = [
        ["body copy", document.body],
        ["homepage explanatory copy", document.querySelector(".landing-lede")],
        ["primary action", document.querySelector(".button-primary")],
        ["sample state", document.querySelector(".landing-sample-label")],
        ["footer support link", document.querySelector("footer a")]
      ].filter(([, element]) => element);
      const disabled = document.createElement("span");
      disabled.className = "button button-disabled";
      disabled.setAttribute("aria-disabled", "true");
      disabled.textContent = "Unavailable";
      document.body.appendChild(disabled);
      pairs.push(["disabled state", disabled]);

      const measured = pairs.map(([label, element]) => {
        const style = getComputedStyle(element);
        const foreground = parse(style.color);
        const background = backgroundFor(element);
        return { label, ratio: foreground ? ratio(foreground.rgb, background) : 0, fontSize: style.fontSize };
      });
      const focusColor = parse(getComputedStyle(document.documentElement).getPropertyValue("--brand-500").trim());
      measured.push({ label: "focus ring on white", ratio: focusColor ? ratio(focusColor.rgb, [255, 255, 255]) : 0, fontSize: "3px" });
      return measured;
    });

    expect(results.length).toBeGreaterThanOrEqual(5);
    for (const result of results) {
      expect(result.ratio, `${result.label} contrast`).toBeGreaterThanOrEqual(4.5);
    }
  });

  test("legal contents disclosure and anchors work with keyboard on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 850 });
    await page.goto("/terms/");

    const rejectCookies = page.getByRole("button", { name: /reject analytics/i });
    if (await rejectCookies.isVisible()) await rejectCookies.click();

    const contents = page.locator(".legal-page-toc-mobile");
    const summary = contents.locator("summary");
    await expect(summary).toBeVisible();
    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(contents).toHaveAttribute("open", "");
    await contents.getByRole("link", { name: "Payments" }).click();
    await expect(page).toHaveURL(/#terms-payments$/);
    await expect(page.locator("#terms-payments")).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });

  test("FAQ groups and disclosures work with keyboard on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await page.goto("/faq/");

    await expect(page.getByRole("heading", { level: 2, name: "Getting started" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "Verification and payments" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: /on this page/i })).toHaveCount(0);

    const paymentSummary = page.getByText("Are payments real?", { exact: true });
    await paymentSummary.focus();
    await page.keyboard.press("Enter");
    await expect(paymentSummary.locator("xpath=.." )).toHaveAttribute("open", "");
    await expect(page.getByText(/Razorpay Test Mode/i)).toBeVisible();
    await page.keyboard.press("Space");
    await expect(paymentSummary.locator("xpath=.." )).not.toHaveAttribute("open", "");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
  });

  test("marketplace filters, pagination, listing, and manufacturer navigation work by keyboard", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto("/marketplace/");

    const filters = page.locator(".marketplace-filter-disclosure");
    const summary = filters.locator("summary");
    const summaryBox = await summary.boundingBox();
    expect(summaryBox.height).toBeGreaterThanOrEqual(44);
    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(filters).toHaveAttribute("open", "");

    const location = page.getByLabel("Location");
    await location.focus();
    await page.keyboard.type("Pune");
    await filters.getByRole("button", { name: /apply filters/i }).focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/location=Pune/);

    const removeLocation = page.getByRole("link", { name: /remove location: pune filter/i });
    const removeBox = await removeLocation.boundingBox();
    expect(removeBox.height).toBeGreaterThanOrEqual(44);
    expect(removeBox.width).toBeGreaterThanOrEqual(44);
    await removeLocation.focus();
    await page.keyboard.press("Enter");
    await expect(page).not.toHaveURL(/location=/);

    await page.goto("/marketplace/");
    const next = page.getByRole("link", { name: /next/i });
    const nextBox = await next.boundingBox();
    expect(nextBox.height).toBeGreaterThanOrEqual(44);
    await next.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/page=2/);

    const listing = page.locator(".listing-spec-main h3 a").first();
    await listing.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator("h1")).toBeVisible();

    const manufacturer = page.locator('a[href*="/manufacturers/"]').first();
    await manufacturer.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/manufacturers\/\d+\//);
  });

  test("reduced motion preference disables reveal dependency", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/marketplace/");

    const hero = page.locator(".marketplace-heading");
    await expect(hero).toBeVisible();
    await expect(hero).toHaveCSS("transform", "none");
  });
});
