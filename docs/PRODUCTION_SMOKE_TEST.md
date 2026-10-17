# Production Smoke Test

Run against the deployed service only with disposable test accounts and non-sensitive data. Do not submit real orders, payments, or credentials during a smoke test.

## Public

- Homepage loads over HTTPS with no broken images or horizontal overflow.
- Marketplace search and filters return expected results.
- Listing detail and manufacturer profile load.
- Informational and legal pages load.
- Mobile navigation opens, closes, and is keyboard accessible.
- A missing route renders the designed 404 page.

## Buyer

- Register and log in with a disposable account.
- Request password reset and confirm the configured email workflow without exposing credentials.
- Save and remove a listing.
- Request a quote.
- Open the buyer dashboard.
- Review quotation accept/decline controls, order view, messages, and notifications using test records only.

## Manufacturer

- Register and log in with a disposable account.
- Open and update the business profile.
- Create and edit a listing, including image fallback behavior.
- Receive a quote request and send a quotation using test data.
- Open the manufacturer dashboard, order milestones, messages, and notifications.

## Infrastructure

- Root domain, `www` domain, and the Render hostname behave as configured.
- HTTP redirects to HTTPS where configured.
- `/health/` returns HTTP 200 and minimal JSON.
- Static files load from the deployed static pipeline.
- Cloudinary images load for configured production media.
- SMTP/password reset works with the configured Brevo settings.
- PostgreSQL is the active production database; do not use local SQLite in production.
- Admin login works and is not exposed through debug output.
