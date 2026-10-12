const { expect } = require("@playwright/test");
const zlib = require("zlib");

function requireEnv(name) {
  const value = process.env[name];

  if (!value) {
    throw new Error(`${name} is required for production E2E tests.`);
  }

  return value;
}

function uniqueRunId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function buildTestUser(prefix, runId) {
  const normalizedPrefix = prefix.toLowerCase().replace(/[^a-z0-9]/g, "");
  const local = `uv-e2e-${normalizedPrefix}-${runId}`.slice(0, 145);

  return {
    username: local,
    email: `${local}@example.com`,
    phone: "9999999999"
  };
}

async function fillAccountFields(page, user, password) {
  await page.locator('[name="username"]').fill(user.username);
  await page.locator('[name="email"]').fill(user.email);
  await page.locator('[name="phone"]').fill(user.phone);
  await page.locator('[name="password1"]').fill(password);
  await page.locator('[name="password2"]').fill(password);
}

async function dismissCookieBanner(page) {
  const rejectButton = page.getByRole("button", { name: /reject analytics/i });

  if (await rejectButton.isVisible().catch(() => false)) {
    await rejectButton.click();
  }
}

async function registerBuyer(page, user, password) {
  await page.goto("/accounts/register/");
  await dismissCookieBanner(page);
  await fillAccountFields(page, user, password);
  await page.getByLabel(/terms.*privacy/i).check();
  await page
    .getByRole("button", { name: /create buyer account/i })
    .click({ noWaitAfter: true });
  await page.waitForURL("**/", { timeout: 45000 });
  await page.waitForLoadState("domcontentloaded", { timeout: 45000 });
  await page.waitForSelector('a[href="/buyer/dashboard/"]', {
    state: "attached",
    timeout: 45000,
  });
}

async function registerManufacturer(page, user, password, profile) {
  await page.goto("/accounts/register/manufacturer/");
  await dismissCookieBanner(page);
  await fillAccountFields(page, user, password);
  await page.locator('[name="business_name"]').fill(profile.businessName);
  await page.locator('textarea[name="description"]').fill(profile.description);
  await page.locator('[name="city"]').fill(profile.city);
  await page.locator('[name="state"]').fill(profile.state);
  await page.getByLabel(/terms.*privacy/i).check();
  await page
    .getByRole("button", { name: /create manufacturer account/i })
    .click({ noWaitAfter: true });
  await page.waitForURL("**/manufacturer/dashboard/", { timeout: 45000 });
  await page.waitForLoadState("domcontentloaded", { timeout: 45000 });
  await expect(page.getByRole("link", { name: /add capacity/i }).first()).toBeVisible({
    timeout: 45000,
  });
}

async function login(page, username, password) {
  await page.goto("/accounts/login/");
  await dismissCookieBanner(page);
  await page.locator('[name="username"]').fill(username);
  await page.locator('[name="password"]').fill(password);
  await page
    .getByRole("button", { name: /^log in$/i })
    .click({ noWaitAfter: true, timeout: 45000 });
  await page.waitForURL(
    (url) => !url.pathname.startsWith("/accounts/login/"),
    { timeout: 45000 }
  );
  await page.waitForLoadState("domcontentloaded", { timeout: 45000 });
}

async function logout(page) {
  await page.getByRole("button", { name: /log out/i }).click();
  await expect(page.getByRole("link", { name: /^log in$/i })).toBeVisible();
}

function tinyPngUpload(name = "uv-e2e-listing.png") {
  return {
    name,
    mimeType: "image/png",
    buffer: createPngBuffer(4, 4)
  };
}

function createPngBuffer(width, height) {
  const signature = Buffer.from("89504e470d0a1a0a", "hex");
  const ihdr = Buffer.alloc(13);
  const rows = [];

  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;

  for (let y = 0; y < height; y += 1) {
    const row = Buffer.alloc(1 + width * 4);
    row[0] = 0;

    for (let x = 0; x < width; x += 1) {
      const offset = 1 + x * 4;

      row[offset] = 36;
      row[offset + 1] = 130;
      row[offset + 2] = 112;
      row[offset + 3] = 255;
    }

    rows.push(row);
  }

  return Buffer.concat([
    signature,
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", zlib.deflateSync(Buffer.concat(rows))),
    pngChunk("IEND", Buffer.alloc(0))
  ]);
}

function pngChunk(type, data) {
  const typeBuffer = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  const crc = Buffer.alloc(4);

  length.writeUInt32BE(data.length, 0);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])), 0);

  return Buffer.concat([length, typeBuffer, data, crc]);
}

function crc32(buffer) {
  let crc = 0xffffffff;

  for (const byte of buffer) {
    crc ^= byte;

    for (let bit = 0; bit < 8; bit += 1) {
      crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
    }
  }

  return (crc ^ 0xffffffff) >>> 0;
}

async function createListing(page, listing) {
  await page.goto("/manufacturer/listings/create/");
  await dismissCookieBanner(page);
  await page.locator('[name="title"]').fill(listing.title);
  await page.locator('[name="category"]').selectOption(listing.category);
  await page.locator('textarea[name="description"]').fill(listing.description);
  await page.locator('[name="machine_type"]').fill(listing.machineType);
  await page.locator('[name="materials"]').fill(listing.materials);
  await page.locator('[name="technical_capabilities"]').fill(listing.capabilities);
  await page.locator('[name="image"]').setInputFiles(tinyPngUpload());
  await page.locator('[name="minimum_quantity"]').fill(String(listing.minimumQuantity));
  await page.locator('[name="price_per_unit"]').fill(String(listing.pricePerUnit));
  await page.locator('[name="batch_price"]').fill(String(listing.batchPrice));
  await page.locator('[name="production_days"]').fill(String(listing.productionDays));
  await page.locator('[name="available_capacity"]').fill(String(listing.availableCapacity));
  await page.locator('[name="capacity_period"]').fill(listing.capacityPeriod);
  await page.locator('[name="cluster"]').fill(listing.cluster);
  await page.locator('[name="availability_status"]').selectOption("AVAILABLE");
  await page.getByRole("button", { name: /save listing/i }).click();
  await expect(page).toHaveURL(/\/manufacturer\/dashboard\/$/);
  await expect(page.getByText(/your listing was saved|your listing was created/i)).toBeVisible();
}

async function adminLogin(page) {
  await page.goto("/admin/login/");
  await page.locator('[name="username"]').fill(requireEnv("TEST_ADMIN_USERNAME"));
  await page.locator('[name="password"]').fill(requireEnv("TEST_ADMIN_PASSWORD"));
  await page.getByRole("button", { name: /log in/i }).click();
  await expect(page.locator("body")).toContainText(/site administration|authentication and authorization|marketplace/i);
}

async function verifyManufacturerInAdmin(page, businessName) {
  await adminLogin(page);
  await page.goto(`/admin/marketplace/manufacturerprofile/?q=${encodeURIComponent(businessName)}`);
  await page.getByRole("link", { name: new RegExp(escapeRegExp(businessName), "i") }).first().click();
  const verified = page.locator('[name="is_verified"]');

  if (!(await verified.isChecked())) {
    await verified.check();
  }

  await page.locator('[name="kyc_status"]').selectOption("VERIFIED");
  await page.locator('[name="_save"]').click();
  await expect(page.locator("body")).toContainText(/was changed successfully|changed successfully/i);
}

async function searchListing(page, listingTitle) {
  await page.goto("/");
  await dismissCookieBanner(page);
  await page.locator('[name="q"]').fill(listingTitle);
  await page.getByRole("button", { name: /search suppliers/i }).click();
  await expect(page.getByRole("link", { name: listingTitle, exact: true })).toBeVisible();
}

async function openListing(page, listingTitle) {
  await searchListing(page, listingTitle);
  await page.getByRole("link", { name: listingTitle, exact: true }).click();
  await expect(page.getByRole("heading", { name: listingTitle })).toBeVisible();
}

async function requestQuote(page, listingTitle, quote) {
  await openListing(page, listingTitle);
  await page.getByRole("link", { name: /request a quote/i }).click();
  await page.locator('[name="quantity"]').fill(String(quote.quantity));
  await page.locator('[name="requirements"]').fill(quote.requirements);
  await page.locator('[name="delivery_location"]').fill(quote.deliveryLocation);
  await page.getByRole("button", { name: /submit quote request/i }).click();
  await expect(page.getByText(/your quote request was submitted/i)).toBeVisible();
  const latestRequest = page.getByText(/your latest saved request: #\d+/i).first();
  await expect(latestRequest).toBeVisible();
  return Number((await latestRequest.textContent()).match(/#(\d+)/)[1]);
}

async function sendQuotation(page, quoteRequestId, quotation) {
  await page.goto("/manufacturer/dashboard/");
  await dismissCookieBanner(page);
  await expect(page.getByText(new RegExp(`Request #${quoteRequestId}\\b`))).toBeVisible();
  await page.getByRole("link", { name: /send quotation/i }).first().click();
  await page.locator('[name="price_per_unit"]').fill(String(quotation.pricePerUnit));
  await page.locator('[name="production_days"]').fill(String(quotation.productionDays));
  await page.locator('[name="message"]').fill(quotation.message);
  await page.getByRole("button", { name: /send quotation/i }).click();
  await expect(page.getByText(/your quotation was sent to the buyer/i)).toBeVisible();
}

async function acceptQuotationAndOpenOrder(page) {
  await page.goto("/my-quote-requests/");
  await expect(page.getByRole("button", { name: /accept quotation/i })).toBeVisible();
  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.getByRole("button", { name: /accept quotation/i }).first().click();
  await expect(page.getByText(/you accepted the quotation/i)).toBeVisible();
  await page.getByRole("link", { name: /view order/i }).first().click();
  await expect(page.getByRole("heading", { name: /order #/i })).toBeVisible();
  return Number(page.url().match(/\/orders\/(\d+)\//)[1]);
}

async function sendOrderMessage(page, orderId, body) {
  await page.goto(`/orders/${orderId}/`);
  await dismissCookieBanner(page);
  await page.locator('[name="body"]').fill(body);
  await page.getByRole("button", { name: /send message/i }).click();
  await expect(page.getByText(/message sent/i)).toBeVisible();
  await expect(page.getByText(body)).toBeVisible();
}

async function fundVisibleMilestone(page, orderId) {
  await page.goto(`/orders/${orderId}/`);
  await dismissCookieBanner(page);
  await page.getByRole("link", { name: /fund milestone \(demo\)/i }).first().click();
  await expect(page.getByRole("heading", { name: /confirm milestone funding/i })).toBeVisible();
  await page.getByRole("button", { name: /confirm demo funding/i }).click();
  await expect(page.getByText(/demo funding confirmed/i).first()).toBeVisible();
}

async function startVisibleMilestone(page, orderId) {
  await page.goto(`/orders/${orderId}/`);
  await dismissCookieBanner(page);
  await page.getByRole("button", { name: /start milestone/i }).first().click();
  await expect(page.getByText(/milestone marked in progress/i)).toBeVisible();
}

async function completeVisibleMilestone(page, orderId) {
  await page.goto(`/orders/${orderId}/`);
  await dismissCookieBanner(page);
  await page.getByRole("button", { name: /submit for approval/i }).first().click();
  await expect(page.getByText(/milestone submitted for buyer approval/i)).toBeVisible();
}

async function approveVisibleMilestone(page, orderId, feedback) {
  await page.goto(`/orders/${orderId}/`);
  await dismissCookieBanner(page);
  await page.locator('[name="buyer_feedback"]').first().fill(feedback);
  await page.getByRole("button", { name: /approve milestone/i }).first().click();
  await expect(page.getByText(/milestone response saved/i)).toBeVisible();
}

async function releaseVisibleMilestone(page, orderId) {
  await page.goto(`/orders/${orderId}/`);
  await dismissCookieBanner(page);
  await page.getByRole("button", { name: /release demo payment/i }).first().click();
  await expect(page.getByText(/demo payment released/i).first()).toBeVisible();
}

async function submitReview(page, orderId, comment) {
  await page.goto(`/orders/${orderId}/review/`);
  await dismissCookieBanner(page);
  await page.locator('[name="quality_rating"]').fill("5");
  await page.locator('[name="timeliness_rating"]').fill("5");
  await page.locator('[name="communication_rating"]').fill("5");
  await page.locator('[name="overall_rating"]').fill("5");
  await page.locator('[name="comment"]').fill(comment);
  await page.getByRole("button", { name: /submit review/i }).click();
  await expect(page.getByText(/thank you for reviewing this order/i)).toBeVisible();
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

module.exports = {
  approveVisibleMilestone,
  buildTestUser,
  completeVisibleMilestone,
  createListing,
  fundVisibleMilestone,
  login,
  logout,
  openListing,
  registerBuyer,
  registerManufacturer,
  requestQuote,
  requireEnv,
  searchListing,
  sendOrderMessage,
  sendQuotation,
  releaseVisibleMilestone,
  startVisibleMilestone,
  submitReview,
  uniqueRunId,
  verifyManufacturerInAdmin,
  acceptQuotationAndOpenOrder,
  dismissCookieBanner
};
