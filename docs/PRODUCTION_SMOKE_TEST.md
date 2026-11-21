# Read-only Production Smoke Checks

Production smoke checks are read-only. Do not register accounts, submit forms,
create listings, request quotations, place orders, send messages, initiate
payments, or otherwise create persistent data in production.

## Public checks

- Homepage and public informational/legal routes load over HTTPS.
- Marketplace, listing detail, and Manufacturer profiles render without broken
  images or horizontal overflow.
- Search and filters can be inspected without submitting data or changing
  records.
- Mobile navigation opens, closes, and remains keyboard accessible.
- A missing route renders the designed 404 page.
- `/health/` returns its expected minimal response.
- Static files and configured public media load.
- HTTP redirects to HTTPS where configured.

Do not use the Playwright data-creating suites against production. Any remote
suite that registers accounts or creates listings/transactions is for an
isolated staging service with disposable data only; see
[`tests/e2e/README.md`](../tests/e2e/README.md).

## Provider checks

Verify domain/DNS, production environment variable names and presence, active
PostgreSQL/TLS configuration, email delivery, media access, and admin access in
the provider dashboards. Do not print credential values in logs or reports.
