# Production Operations

## Deployment flow

1. Review the branch and working tree; do not deploy uncommitted changes.
2. Run `python manage.py check`, `python manage.py makemigrations --check --dry-run`, focused tests, and `python manage.py test`.
3. Review the diff and commit the change.
4. Deploy through the approved Render workflow. The repository build flow installs requirements, collects static files, and runs migrations.
5. Review Render logs and complete the smoke checklist before declaring the deploy healthy.

Do not run seed or destructive data commands as part of the build flow.

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
- `SENTRY_DSN=` enables Sentry only when populated; leave it blank to keep Sentry disabled.
- `SENTRY_ENVIRONMENT=production` identifies the deployment environment.
- `SENTRY_RELEASE=` optionally identifies the deployed release.
- `SENTRY_TRACES_SAMPLE_RATE=0` keeps performance tracing disabled by default.

Sentry keeps `send_default_pii` disabled, does not capture request bodies, and removes request headers, cookies, query strings, user data, extras, and breadcrumb data before sending an event. It complements Render console logs and does not replace them. To verify it after deployment, configure the DSN, deploy, and cause a controlled error in a protected local/staging-only workflow or a temporary authenticated diagnostic command; do not add a public debug route or trigger an event from a public endpoint. If Sentry fails, use the Render logs and check the DSN/environment/release settings without printing the DSN.

## Verify a deploy

- Confirm the Render deploy completes without build, migration, or startup errors.
- Request `/health/` and expect only `{"status":"ok"}` with HTTP 200.
- Check the canonical URL, root and `www` host behavior, HTTPS redirect, `/robots.txt`, `/sitemap.xml`, and static assets.
- Open the homepage, search/filter results, listing detail, login, and one informational page.
- Confirm Cloudinary listing images load and local fallback images still render.
- Confirm password reset uses the configured email backend without exposing credentials.
- Review logs for unexpected 4xx/5xx errors; never paste secrets or full request bodies into tickets.

## Rollback and diagnosis

- Roll back through the approved Render/Git workflow to a previously reviewed commit; do not reset or rewrite shared history.
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
