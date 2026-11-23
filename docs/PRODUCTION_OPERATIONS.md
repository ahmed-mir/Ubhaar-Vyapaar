# Production Operations

## Deployment flow

1. Review the branch and working tree; do not deploy uncommitted changes.
2. Run `python manage.py check`, `python manage.py makemigrations --check --dry-run`, focused tests, and `python manage.py test`.
3. Review the diff and commit the change.
4. Deploy through the approved Render workflow. The repository `build.sh` runs `pip install -r requirements.txt`, `python manage.py collectstatic --noinput`, then `python manage.py migrate`.
5. The repository has no Render service manifest or Procfile, so confirm the configured Render start command in the dashboard. Confirm required environment variables are present during both build and runtime; production settings require `DATABASE_URL` during management commands too.
6. Review Render logs and complete the read-only smoke checklist before declaring the deploy healthy.

Do not run seed or destructive data commands as part of the build flow.

Before deployment, complete [`PROVIDER_VERIFICATION_CHECKLIST.md`](PROVIDER_VERIFICATION_CHECKLIST.md).

## Environment variables by function

**Core and domain**
- `DJANGO_SECRET_KEY` — required secret key; never print or commit it.
- `DJANGO_DEBUG` — set `False` in production.
- `DJANGO_ALLOWED_HOSTS` — comma-separated production hosts, including the configured root, `www`, and Render host as needed.
- `DJANGO_CSRF_TRUSTED_ORIGINS` — comma-separated `https://` origins used for trusted form posts.
- `SITE_ORIGIN` — canonical public origin; default is `https://ubhaar-vyapaar.in`.

**Database**
- `DATABASE_URL` — managed PostgreSQL connection URL in production.

**Email**
- `DJANGO_EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL`, and optionally `DJANGO_DEFAULT_FROM_EMAIL`, `SERVER_EMAIL`, `DJANGO_SERVER_EMAIL`, `DJANGO_ADMINS`.
- Brevo SMTP should use the provider-approved host, credentials, TLS mode, and port (commonly 2525 where required by the runtime).

**Media**
- `DJANGO_USE_CLOUDINARY_MEDIA`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, and optional `CLOUDINARY_MEDIA_PREFIX`.

**Analytics and legal content**
- `GOOGLE_ANALYTICS_ID` is optional and remains inactive when unset or until consent is granted.
- `LEGAL_ENTITY_NAME`, `LEGAL_CONTACT_EMAIL`, `LEGAL_CONTACT_LABEL`, `TERMS_VERSION`, and `PRIVACY_POLICY_VERSION` are configuration values; do not invent missing business details.

**Optional Sentry monitoring**
- Supported variable names are `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`, `RENDER_GIT_COMMIT`, and `SENTRY_TRACES_SAMPLE_RATE`. Leave `SENTRY_DSN` unset to keep Sentry disabled. `DEBUG=True`, Django tests, and local Playwright E2E settings disable Sentry even if the parent environment contains a DSN.
- The default environment label is `production` with `DEBUG=False` and `development` with `DEBUG=True`. Release uses `SENTRY_RELEASE`, then `RENDER_GIT_COMMIT` if available. Tracing defaults to `0.0`.

Sentry keeps `send_default_pii` disabled, disables local-variable capture, and removes request bodies, headers, cookies, query strings (including the URL query), user data, extras, and breadcrumb data before sending an event. Tests do not initialize Sentry. It complements Render console logs and does not replace them. Never put credentials, reset tokens, payment signatures, or raw throttle identifiers in application log messages.

The repository has no custom `handler400`, `handler403`, `handler404`, or
`handler500` routing. Production uses `DEBUG=False`; inspect Django/Render error
logs for failures and never enable debug tracebacks in production.

The Phase 3 workflow schema change (`0019`) is additive and uses nullable unique
action digests for existing Orders and QuoteRequests. Phase 4 adds no schema
changes. Review the deployed migration state before a code rollback; do not
reverse a migration blindly.

## Health, readiness, and monitoring

- `/health/` is a cheap process liveness response and does not query the database.
- `/ready/` runs `SELECT 1` on the default database. It returns HTTP 200 with `{"status":"ready"}` or HTTP 503 with `{"status":"not_ready"}`. PostgreSQL readiness queries use a transaction-local 3-second statement timeout; production connection establishment has a 10-second default timeout unless the URL already configures one.
- Configure Render's health-check path to `/health/` so a temporary database outage does not trigger restart loops. Optionally monitor `/ready/` separately for dependency availability.
- Provider-side alerts are not configured in this repository. Decide destinations and thresholds for service unavailability, readiness/database failures, elevated 5xx responses, payment verification failures, Sentry error spikes, and failed deploys.

## Authentication throttle cleanup

Schedule `python manage.py prune_auth_throttles` once daily through a provider-managed scheduled job. Run it from the application root with the same release's virtual environment, settings, and production database environment as the web service. No scheduler is configured here. If cleanup is delayed, expired buckets stop blocking requests automatically, but old rows continue to accumulate. The command is idempotent and reports only a total row count; it does not print identifiers. Do not use cleanup as a substitute for investigating database incidents.

## Verify a deploy

- Confirm the Render deploy completes without build, migration, or startup errors.
- Request `/health/` and expect only `{"status":"ok"}` with HTTP 200.
- Request `/ready/` and expect only `{"status":"ready"}` with HTTP 200.
- Check the canonical URL, root and `www` host behavior, HTTPS redirect, `/robots.txt`, `/sitemap.xml`, and static assets.
- Open the homepage, search/filter results, listing detail, login, and one informational page.
- Confirm Cloudinary listing images load and local fallback images still render.
- Confirm password reset uses the configured email backend without exposing credentials.
- Review logs for unexpected 4xx/5xx errors; never paste secrets or full request bodies into tickets.

Use the read-only checks in [`PRODUCTION_SMOKE_TEST.md`](PRODUCTION_SMOKE_TEST.md). Do not run data-creating Playwright E2E suites against production; remote data-creating E2E is restricted to an isolated staging service.

## Rollback and diagnosis

- **Code rollback:** use the approved Render/Git workflow to redeploy a previously reviewed known-good commit; do not reset or rewrite shared history. Confirm the previous code remains compatible with the current schema before redeploying.
- **Database rollback:** is a separate recovery decision, not an automatic consequence of code rollback. Do not blindly reverse migrations or restore over production. Follow `PRODUCTION_DATABASE_RUNBOOK.md`; restore to a separate non-production target first whenever possible.
- **Failed migration:** stop the deploy/retry loop, record the migration and failure, inspect the database's applied migration state and the migration's atomic/reversible properties, then agree on a forward repair or provider restore plan. Do not repeatedly run destructive commands blindly.
- Diagnose a 500 from Render logs using the timestamp, route, request ID if available, and exception type. Do not enable `DEBUG` in production.
- For SMTP failures, verify host, port, TLS, sender authentication, timeout, and provider status without logging the password.
- For Cloudinary failures, verify all three credentials and the media toggle in Render; do not migrate or delete media.
- For database incidents, follow `docs/PRODUCTION_DATABASE_RUNBOOK.md` and verify provider backup status before any repair.
- If the service is sleeping or spinning up, check Render instance state, startup logs, health response, and database connection availability.
- For custom-domain failures, check DNS records, Render custom-domain status, certificate issuance, `ALLOWED_HOSTS`, CSRF origins, and HTTPS redirects.

## Emergency checklist

1. Record the incident time and affected route.
2. Check Render service, deploy, database, SMTP, Cloudinary, and custom-domain status.
3. Preserve relevant logs without secrets or personal data.
4. Avoid migrations, seed commands, media deletion, or database changes until the failure mode is understood.
5. Roll back only to a reviewed commit when rollback is safer than repair.
6. Re-run the smoke checklist and document the recovery.
