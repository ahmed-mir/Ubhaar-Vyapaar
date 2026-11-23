# Production Provider Verification Checklist

Repository configuration does not prove dashboard settings are enabled. An
operator must verify each item below in the relevant provider account before
launch. Record the verifier and date in the team's restricted operations
record; do not copy credential values into this checklist.

## Render

- [ ] `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY`, and the intended PostgreSQL
  `DATABASE_URL` are set for the production service.
- [ ] Confirm the production start command in the service dashboard. No
  `render.yaml` or `Procfile` defines it in this repository.
- [ ] Confirm build and runtime environments both receive the required
  variables. `build.sh` installs requirements, runs `collectstatic`, then
  applies migrations.
- [ ] Set the service health-check path to `/health/`; monitor `/ready/`
  separately if dependency readiness alerts are desired.
- [ ] Confirm instance count, deploy history, and the procedure for redeploying
  a previously reviewed commit.
- [ ] Confirm logs are retained and alerts reach an on-call owner for failed
  deploys, unavailable service, readiness failures, and elevated 5xx responses.

## Neon / PostgreSQL

- [ ] Confirm the intended production database/branch and enforced TLS.
- [ ] Verify current-plan automated backup and PITR availability, recovery
  granularity, and the actual retention window; do not assume a value.
- [ ] Confirm who can create branches, restore data, and authorize cutover.
- [ ] Verify access controls, credential storage/rotation policy, and the
  separate non-production target for restore drills.
- [ ] Agree and record service RPO and RTO; repository defaults remain TBD.

## Cloudflare

- [ ] Confirm DNS/proxy status and HTTPS mode/certificate behavior.
- [ ] Verify WAF and rate limits for authentication and other sensitive routes.
- [ ] Confirm origin protection and trusted forwarding behavior between
  Cloudflare and Render. The application does not treat arbitrary
  `X-Forwarded-For` as trusted client identity.

## Sentry

- [ ] Confirm the intended project DSN is stored only in the provider's secret
  environment configuration as `SENTRY_DSN`.
- [ ] Confirm `SENTRY_ENVIRONMENT` and release identification are correct.
- [ ] Confirm alert rules and their destination reach a responsible operator.
- [ ] Review PII settings. Application initialization sets
  `send_default_pii=False` and scrubs request content/headers/cookies/query data.

## Email provider

- [ ] Confirm credentials are stored in Render environment settings and SMTP
  uses the provider's supported TLS configuration.
- [ ] Verify sender-domain SPF, DKIM, and DMARC records and delivery/failure
  alerts.

## Razorpay

- [ ] Confirm account MFA and who can manage API keys/webhooks.
- [ ] Verify the configured credentials are Test Mode or Live Mode as intended;
  this application is currently designed for Test Mode.
- [ ] Verify the deployed webhook URL, subscribed events, and signing secret
  without copying secret values into tickets or logs.

## GitHub and operator accounts

- [ ] Verify MFA for GitHub and provider/operator accounts where supported.
- [ ] Review main-branch protection, required reviews/checks, secret scanning,
  and Dependabot configuration.

No provider dashboard was inspected as part of this repository work; none of
these checks should be assumed complete until an operator records verification.
