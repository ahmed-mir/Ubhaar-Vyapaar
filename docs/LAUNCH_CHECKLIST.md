# Launch Checklist

- [ ] Merge `phase-18-launch-readiness` into main after review.
- [ ] Trigger Render deploy from the intended production branch.
- [ ] Run migrations on production.
- [ ] Confirm `collectstatic` succeeds during build.
- [ ] Confirm Cloudinary credentials and media delivery.
- [ ] Configure SMTP and test password reset email.
- [ ] Set `GOOGLE_ANALYTICS_ID` if analytics should be enabled.
- [ ] Confirm production admin access.
- [ ] Configure domain DNS.
- [ ] Add custom domain to `DJANGO_ALLOWED_HOSTS`.
- [ ] Add HTTPS origins to `DJANGO_CSRF_TRUSTED_ORIGINS`.
- [ ] Confirm HTTPS redirect and certificate.
- [ ] Confirm `www` redirect preference.
- [ ] Test password reset end to end.
- [ ] Verify cookie consent and analytics consent behavior.
- [ ] Verify `/sitemap.xml`.
- [ ] Verify `/robots.txt`.
- [ ] Run buyer smoke test: signup, quote request, order, milestone, review.
- [ ] Run manufacturer smoke test: signup, listing, quotation, order, milestone.

## Local Demo Data Reset

For disposable local development data only, reseed demo listings with:

```bash
python manage.py seed_demo_data
```

To clear old local E2E records such as `UV E2E Verified Capacity ...`, use Django admin and delete only those obvious test records, or reset a disposable local database and run migrations before reseeding. Do not run local cleanup steps against production data.
