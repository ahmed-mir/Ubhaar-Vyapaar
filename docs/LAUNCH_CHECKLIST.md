# Launch Checklist

## Deployment and provider checks

- [ ] Review and approve the release branch before merging it to `main`.
- [ ] Trigger the Render deploy from the intended production branch.
- [ ] Confirm production migrations and `collectstatic` complete successfully.
- [ ] Confirm Cloudinary configuration and media delivery.
- [ ] Configure SMTP and verify password-reset delivery with an approved test account.
- [ ] Set `GOOGLE_ANALYTICS_ID` only if analytics should be enabled.
- [ ] Confirm authorized production Admin access.
- [ ] Configure domain DNS, HTTPS, and the `www` redirect preference.
- [ ] Add the production host to `DJANGO_ALLOWED_HOSTS` and HTTPS origins to `DJANGO_CSRF_TRUSTED_ORIGINS`.
- [ ] Verify cookie consent and analytics consent behavior.
- [ ] Verify `/sitemap.xml` and `/robots.txt`.

## Routine production smoke checks

Routine post-deploy production smoke testing is read-only and non-destructive. Use the current [production smoke checklist](PRODUCTION_SMOKE_TEST.md). Do not create accounts, listings, quote requests, quotations, orders, messages, payment transactions, or close accounts as part of routine production smoke testing.

Use existing authorized test accounts only for read-only dashboard, Order, privacy-export, or Admin checks. Do not modify production workflow or account state merely to verify that a page renders.

## Write-flow validation

Validate signup, Request Quote, Buy Now, quotation acceptance, milestone transitions, messaging, and payment initiation in staging or another isolated test environment. If a production write-flow test is exceptionally necessary, first obtain explicit operator approval and use a designated test account with known test data and a documented cleanup plan. Payment checks must use Razorpay Test Mode; do not create arbitrary production payment transactions.

Account-closure testing belongs in staging or an isolated test account. Never close a real production account as a smoke test.

## Local demo data reset

For disposable local development data only, reseed demo listings with:

```bash
python manage.py seed_demo_data
```

To clear old local E2E records such as `UV E2E Verified Capacity ...`, use Django Admin to delete only those obvious test records, or reset a disposable local database and run migrations before reseeding. Do not run local cleanup steps against production data.
