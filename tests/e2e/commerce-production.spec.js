const { test, expect } = require("@playwright/test");

const {
  approveVisibleMilestone,
  buildTestUser,
  completeVisibleMilestone,
  createListing,
  fundVisibleMilestone,
  logout,
  openListing,
  registerBuyer,
  registerManufacturer,
  requestQuote,
  requireEnv,
  sendOrderMessage,
  sendQuotation,
  releaseVisibleMilestone,
  startVisibleMilestone,
  submitReview,
  uniqueRunId,
  verifyManufacturerInAdmin,
  acceptQuotationAndOpenOrder,
} = require("./helpers");

const hasAdminCredentials = Boolean(
  process.env.TEST_ADMIN_USERNAME &&
    process.env.TEST_ADMIN_PASSWORD
);

test.describe("production commerce smoke", () => {
  test.skip(
    !hasAdminCredentials,
    "KYC-dependent marketplace/order flow requires TEST_ADMIN_USERNAME and TEST_ADMIN_PASSWORD."
  );

  test(
    "verified listing, quote, order, milestones, messages, notifications, and review",
    async ({ browser }) => {
      // This is a long production E2E test against Render Free,
      // so allow up to 4 minutes.
      test.setTimeout(240000);

      const password = requireEnv("TEST_USER_PASSWORD");
      const runId = uniqueRunId();

      const buyer = buildTestUser("commerce-buyer", runId);
      const otherBuyer = buildTestUser("other-buyer", runId);
      const manufacturer = buildTestUser("commerce-mfr", runId);

      const businessName = `UV E2E Verified Works ${runId}`;
      const listingTitle = `UV E2E Verified Capacity ${runId}`;
      const quoteRequirements =
        `Smoke-test package requirements ${runId}`;

      let quoteRequestId;
      let orderId;

      const buyerContext = await browser.newContext();
      const manufacturerContext = await browser.newContext();
      const adminContext = await browser.newContext();
      const otherBuyerContext = await browser.newContext();

      const buyerPage = await buyerContext.newPage();
      const manufacturerPage =
        await manufacturerContext.newPage();
      const adminPage = await adminContext.newPage();
      const otherBuyerPage =
        await otherBuyerContext.newPage();

      try {
        await test.step(
          "create disposable buyer and manufacturer",
          async () => {
            await registerBuyer(
              buyerPage,
              buyer,
              password
            );

            await registerManufacturer(
              manufacturerPage,
              manufacturer,
              password,
              {
                businessName,
                description:
                  "Disposable verified manufacturer for production smoke tests.",
                city: "Ahmedabad",
                state: "Gujarat",
              }
            );
          }
        );

        await test.step(
          "manufacturer creates listing with image upload",
          async () => {
            await createListing(manufacturerPage, {
              title: listingTitle,
              category: "PACKAGING",
              description:
                "Disposable public listing for end-to-end production smoke tests.",
              machineType:
                "Digital cutting and packing line",
              materials:
                "Corrugated board, labels, kraft paper",
              capabilities:
                "Prototype packaging, dieless cutting, labeling, and assembly.",
              minimumQuantity: 20,
              pricePerUnit: "18.75",
              batchPrice: "375.00",
              productionDays: 5,
              availableCapacity: 900,
              capacityPeriod: "per week",
              cluster:
                "Ahmedabad industrial estate",
            });
          }
        );

        await test.step(
          "admin verifies disposable manufacturer",
          async () => {
            await verifyManufacturerInAdmin(
              adminPage,
              businessName
            );
          }
        );

        await test.step(
          "listing is visible in marketplace with production media URL",
          async () => {
            await openListing(
              buyerPage,
              listingTitle
            );

            const imageSrc = await buyerPage
              .locator(`img[alt="${listingTitle}"]`)
              .first()
              .getAttribute("src");

            expect(imageSrc).toMatch(
              /^https:\/\/res\.cloudinary\.com\//
            );
          }
        );

        await test.step(
          "buyer saves listing",
          async () => {
            await buyerPage
              .getByRole("button", {
                name: /save listing/i,
              })
              .click();

            await expect(
              buyerPage.getByText(/listing saved/i)
            ).toBeVisible();

            await buyerPage.goto(
              "/saved-listings/"
            );

            await expect(
              buyerPage.getByRole("heading", {
                name: listingTitle,
              })
            ).toBeVisible();
          }
        );

        await test.step(
          "buyer requests quote",
          async () => {
            quoteRequestId = await requestQuote(
              buyerPage,
              listingTitle,
              {
                quantity: 30,
                requirements:
                  quoteRequirements,
                deliveryLocation:
                  "Mumbai, Maharashtra",
              }
            );
          }
        );

        await test.step(
          "manufacturer sends quotation",
          async () => {
            await sendQuotation(
              manufacturerPage,
              quoteRequestId,
              {
                pricePerUnit: "21.25",
                productionDays: 6,
                message:
                  `Quotation generated by production smoke test ${runId}.`,
              }
            );
          }
        );

        await test.step(
          "buyer accepts quotation and order is created",
          async () => {
            orderId =
              await acceptQuotationAndOpenOrder(
                buyerPage
              );

            await expect(
              buyerPage.getByText(
                quoteRequirements
              )
            ).toBeVisible();
          }
        );

        await test.step(
          "order-scoped messaging and notifications work",
          async () => {
            await sendOrderMessage(
              buyerPage,
              orderId,
              `Buyer scoped message ${runId}`
            );

            await manufacturerPage.goto(
              `/orders/${orderId}/`
            );

            await expect(
              manufacturerPage.getByText(
                `Buyer scoped message ${runId}`
              )
            ).toBeVisible();

            await manufacturerPage.goto(
              "/notifications/"
            );

            await expect(
              manufacturerPage.getByText(
                new RegExp(
                  `New message on order #${orderId}`,
                  "i"
                )
              )
            ).toBeVisible();

            await sendOrderMessage(
              manufacturerPage,
              orderId,
              `Manufacturer scoped reply ${runId}`
            );

            await buyerPage.goto(
              `/orders/${orderId}/`
            );

            await expect(
              buyerPage.getByText(
                `Manufacturer scoped reply ${runId}`
              )
            ).toBeVisible();

            await buyerPage.goto(
              "/notifications/"
            );

            await expect(
              buyerPage.getByText(
                new RegExp(
                  `New message on order #${orderId}`,
                  "i"
                )
              )
            ).toBeVisible();
          }
        );

        await test.step(
          "unrelated buyer cannot access order or messages",
          async () => {
            await registerBuyer(
              otherBuyerPage,
              otherBuyer,
              password
            );

            const detailResponse =
              await otherBuyerPage.goto(
                `/orders/${orderId}/`
              );

            expect([403, 404]).toContain(
              detailResponse.status()
            );

            const cookies =
              await otherBuyerPage
                .context()
                .cookies();

            const csrfToken = cookies.find(
              (cookie) =>
                cookie.name === "csrftoken"
            )?.value;

            const messageResponse =
              await otherBuyerPage.request.post(
                `/orders/${orderId}/messages/send/`,
                {
                  form: {
                    body:
                      `Unauthorized message attempt ${runId}`,
                  },
                  headers: csrfToken
                    ? {
                        "X-CSRFToken":
                          csrfToken,
                      }
                    : undefined,
                }
              );

            expect([403, 404]).toContain(
              messageResponse.status()
            );
          }
        );

        await test.step(
          "demo milestone funding workflow completes order",
          async () => {
            await fundVisibleMilestone(
              buyerPage,
              orderId
            );

            await startVisibleMilestone(
              manufacturerPage,
              orderId
            );

            await completeVisibleMilestone(
              manufacturerPage,
              orderId
            );

            await approveVisibleMilestone(
              buyerPage,
              orderId,
              `Approved first milestone ${runId}`
            );

            await releaseVisibleMilestone(
              buyerPage,
              orderId
            );

            await fundVisibleMilestone(
              buyerPage,
              orderId
            );

            await startVisibleMilestone(
              manufacturerPage,
              orderId
            );

            await completeVisibleMilestone(
              manufacturerPage,
              orderId
            );

            await approveVisibleMilestone(
              buyerPage,
              orderId,
              `Approved final milestone ${runId}`
            );

            await releaseVisibleMilestone(
              buyerPage,
              orderId
            );

            await buyerPage.goto(
              `/orders/${orderId}/`
            );

            await expect(
              buyerPage
                .getByText(/completed/i)
                .first()
            ).toBeVisible();

            await expect(
              buyerPage.getByRole("link", {
                name: /write review/i,
              })
            ).toBeVisible();
          }
        );

        await test.step(
          "buyer creates one review and duplicate review is prevented",
          async () => {
            const reviewComment =
              `Completed order review from production smoke test ${runId}.`;

            await submitReview(
              buyerPage,
              orderId,
              reviewComment
            );

            await expect(
              buyerPage.getByText(
                reviewComment
              )
            ).toBeVisible();

            await buyerPage.goto(
              `/orders/${orderId}/review/`
            );

            await expect(
              buyerPage.getByText(
                /you already reviewed this order/i
              )
            ).toBeVisible();

            await expect(
              buyerPage
            ).toHaveURL(
              new RegExp(
                `/orders/${orderId}/$`
              )
            );
          }
        );

        await logout(buyerPage);
        await logout(manufacturerPage);
      } finally {
        await buyerContext.close();
        await manufacturerContext.close();
        await adminContext.close();
        await otherBuyerContext.close();
      }
    }
  );
});
