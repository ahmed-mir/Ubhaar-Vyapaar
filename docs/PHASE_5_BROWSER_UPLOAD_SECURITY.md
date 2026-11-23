# Phase 5: browser and upload security

## Content Security Policy

Django 6.1's `ContentSecurityPolicyMiddleware` enforces the policy in
`config/settings.py`. It uses a per-response nonce for the existing inline
scripts and Django Admin templates, including Django Admin's nonce-bearing
inline changelist styles. The site does not use `unsafe-inline`,
`unsafe-eval`, or wildcard sources. Inline event-handler attributes are
disallowed; listing-image fallback behavior is implemented in a same-origin
script instead.

Allowed non-self origins are limited to:

- `https://res.cloudinary.com` for public listing images delivered by the
  configured secure Cloudinary storage.
- `https://checkout.razorpay.com` for the existing Razorpay Checkout script
  and its documented browser integration.
- `https://api.razorpay.com` for the Checkout frame and browser API calls.
- `https://www.googletagmanager.com` for the optional Google Analytics script,
  loaded only after analytics consent.
- `https://www.google-analytics.com` and
  `https://region1.google-analytics.com` for consented analytics collection
  and its image fallback.

There are no externally hosted stylesheets or fonts. `default-src` and the
resource-specific policies are self-only unless an origin above is required.
`object-src` is `none`; `base-uri` and `form-action` are self-only;
`frame-ancestors` is `none`. Production adds `upgrade-insecure-requests`; local
HTTP development and tests do not. The policy is enforced directly, with no
remote report collector.

`Permissions-Policy` disables camera, microphone, geolocation, USB, and
Bluetooth. The `payment` feature is deliberately left at the browser's normal
default because the repository does not establish whether the external
Razorpay Checkout uses Payment Request API. The application itself does not
call that API. `X-Frame-Options: DENY` remains in place.

COOP, CORP, and COEP are intentionally deferred because cross-origin checkout
and provider assets have not been validated against those isolation headers.

## Request and upload limits

- `DATA_UPLOAD_MAX_MEMORY_SIZE` is 10 MiB. Django applies this limit to
  non-file form data; uploaded file bytes are excluded by Django's multipart
  parser.
- `FILE_UPLOAD_MAX_MEMORY_SIZE` remains 2.5 MiB. Larger uploads spool to
  temporary storage rather than remaining entirely in memory.
- Django accepts at most one file per request. The product currently has one
  upload field: the optional listing image.
- A listing image is limited to 5 MiB based on streamed bytes. The upload
  handler stops passing an over-limit image to the memory/temp-file handlers;
  the listing form renders a field error and does not save the listing.
- Pillow's `ImageField` opens and verifies image data. The form then permits
  only JPEG, PNG, and WebP, and rejects dimensions above 20,000,000 pixels.
  SVG, GIF, and BMP are not accepted for listing uploads.
- Django sanitizes uploaded names before storage. Cloudinary storage uploads
  images with `resource_type="image"` and generates secure HTTPS URLs; local
  development uses filesystem storage.

`DATA_UPLOAD_MAX_MEMORY_SIZE` is not a total multipart-body cap because Django
excludes file bytes. The file size is independently limited while Django
streams it, then checked again by form validation. The separate upload-memory
threshold controls memory versus temporary-file storage.

## Verification limits

Automated tests use local storage and do not contact Cloudinary or Razorpay.
The Razorpay script, frame, and API origins are explicitly allowlisted from the
current integration; a real provider checkout session was not opened as part
of this code change. Review browser CSP violation logs during a future
provider-authorized Test Mode checkout before enabling any additional origin.
