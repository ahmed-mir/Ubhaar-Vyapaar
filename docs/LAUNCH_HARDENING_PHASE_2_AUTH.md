# Authentication abuse protection (internal)

## Protected endpoints and defaults

| Endpoint | Protection | Default |
| --- | --- | --- |
| `/accounts/login/` | django-axes database-backed identifier limit plus a pseudonymous browser-source limit | 5 failures per identifier per 15 minutes; 30 login submissions per browser source per 15 minutes |
| `/admin/` login | django-axes database-backed identifier limit | 5 failures per identifier per 15 minutes |
| `/accounts/password/reset/` | HMAC-keyed database windows for normalized email and browser source | 3 requests per email per hour; 8 per browser source per hour |
| Buyer and Manufacturer registration POSTs | HMAC-keyed shared database window, counted after form validation | 8 valid submissions per browser source per hour |

The account identifier and browser-source counters are stored as keyed HMAC digests. Passwords, reset tokens, cookies, and raw session IDs are not written to throttle records. django-axes masks password, identifier, CSRF, and token fields in its diagnostic request data and stores a pseudonymized username. Login errors remain generic. A successful login clears the matching account attempt history; email logins also clear the submitted email digest.

No forwarded client-IP header is trusted by application code. The source counters use a random, signed, HttpOnly browser marker cookie. Only its keyed digest is persisted in the limiter table. This is defense in depth and can be bypassed by a determined client that discards cookies. Application limits are not a substitute for an upstream WAF or origin controls.

## Configuration

The following environment variable names can adjust the defaults. Values must be positive integers:

- `AUTH_LOGIN_LIMIT`
- `AUTH_LOGIN_WINDOW_SECONDS`
- `AUTH_LOGIN_SOURCE_LIMIT`
- `PASSWORD_RESET_LIMIT`
- `PASSWORD_RESET_WINDOW_SECONDS`
- `PASSWORD_RESET_SOURCE_LIMIT`
- `PASSWORD_RESET_SOURCE_WINDOW_SECONDS`
- `SIGNUP_LIMIT`
- `SIGNUP_WINDOW_SECONDS`

No new secret variables are required. Existing `DJANGO_SECRET_KEY` is used as HMAC key material; changing it invalidates existing pseudonymous buckets and login-attempt identifiers.

## Expiry and maintenance

Requests automatically use a new fixed-window bucket after the configured window; expired buckets do not block later requests. django-axes expires attempts on subsequent login traffic. Run this command periodically (for example, from a private Render Cron job) to remove old limiter records:

```text
python manage.py prune_auth_throttles
```

If a temporary throttle must be cleared after verifying the affected user/source through the normal support process, an operator can clear only limiter state with:

```text
python manage.py reset_auth_throttles --confirm
```

This clears all current authentication limiter state and does not change user accounts. Use only from an authenticated, private operations context. It is not intended as a routine bypass.

## Operational follow-up before launch

- Verify Cloudflare WAF/rate-limit rules, origin protection, and the trusted forwarding chain for the deployed origin.
- Verify Render proxy/header behavior and instance count. This application does not trust `X-Forwarded-For` for client identity.
- Verify MFA is enabled for GitHub, Render, Neon, Cloudflare, Cloudinary, Razorpay, email provider, and Sentry operator accounts where supported. Application-level MFA is not implemented.
- Verify provider alerts and account recovery contacts independently in each provider dashboard.

Application-side thresholds are centralized in Django settings. Multi-worker limiter state is stored in the configured Django database; Phase 1 E2E settings continue to use the isolated local E2E SQLite database.
