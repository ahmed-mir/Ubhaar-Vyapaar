# Authentication abuse protection (internal)

## Protected endpoints and defaults

| Endpoint | Protection | Default |
| --- | --- | --- |
| `/accounts/login/` | HMAC-keyed database fixed-window identifier failures plus a pseudonymous browser-source limit | Failures 1–4 show the generic login error; failure 5 and later attempts in that same 15-minute fixed window are throttled. 30 login submissions per browser source per 15-minute fixed window. |
| `/admin/` login | The same HMAC-keyed database fixed-window identifier failure limiter using Django Admin's authentication form | Failure 5 and later attempts in the same 15-minute fixed window are throttled. |
| `/accounts/password/reset/` | HMAC-keyed database windows for normalized email and browser source | 3 requests per email per hour; 8 per browser source per hour |
| Buyer and Manufacturer registration POSTs | HMAC-keyed shared database window, counted after form validation | 8 valid submissions per browser source per hour |

The identifier and browser-source counters are stored as keyed HMAC digests in `AuthRateLimitBucket`. Login failures use fixed windows aligned to epoch multiples of the configured duration: a new 15-minute window starts at each quarter-hour boundary. Only failed authentication attempts count; the request that records failure 5 is throttled. A successful public or Admin login clears that normalized identifier's failure buckets. It does not clear browser-source counters. Passwords, reset tokens, cookies, and raw session IDs are never written to limiter records. Login errors and throttled login responses remain generic.

No forwarded client-IP header is trusted by application code. Source counters use a random, signed, HttpOnly browser marker cookie with `SameSite=Lax` and `Secure` when production session cookies are Secure. Only its keyed digest is persisted in the limiter table. Clearing, rejecting, or omitting the cookie can evade this source dimension; it is defense in depth, not IP-based protection. Application limits are not a substitute for an upstream WAF or origin controls.

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

Requests automatically use a new fixed-window bucket after the configured window; expired buckets do not block later requests even if cleanup is delayed. The cleanup command removes only scopes' prior windows, preserves current active windows, and is safe to run repeatedly. **Schedule `prune_auth_throttles` daily in production** using the deployment's private scheduled-job facility (for example, a Render Cron job). Actual provider-side scheduling remains an operations task; no scheduler is configured in this repository.

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
