# Phase 7: privacy and data lifecycle

Internal operations note. The public Privacy Policy was updated for the
implemented export and account-closure behavior. Obtain qualified legal review
of the policy, legal bases, retention decisions, and provider terms before
launch. No statutory retention period or compliance certification is asserted
here.

## Data classification and current model links

| Class | Project records and fields | Current lifecycle |
| --- | --- | --- |
| Account/profile personal data | `accounts.User` (username, email, name, phone, role, consent metadata); `ManufacturerProfile` (business name, description, city/state/PIN, verification) | Eligible self-service closure anonymizes account identifiers and contact/profile fields, marks the account inactive, and makes the password unusable. Manufacturer public profile is hidden and listings are deactivated. Retention duration: policy decision required. |
| Marketplace records | `QuoteRequest`, `Quotation`, `Order`, `Milestone`, `Review`, listing snapshots | Active obligations block closure. Historical rows and foreign keys are retained. Buyer `QuoteRequest.requirements` and `delivery_location` are cleared on eligible closure. Historical Order `requirements` snapshots are retained as the commercial scope captured at transaction time; structured delivery fields in those snapshots are cleared where implemented. Retention duration: TBD / policy decision required. |
| Payment / webhook records | `PaymentTransaction`, `PaymentWebhookEvent` | No account-closure mutation. Provider IDs, amounts, currency, status, webhook event identifiers, and processing state remain unchanged. Retention duration and provider requirements: policy decision required. |
| User communications | `OrderMessage`, `Quotation.message`, notifications | On closure, the user's own order-message bodies are replaced with a generic removal marker; Buyer RFQ fields are cleared; quotation messages remain as historical negotiation/transaction context and are not automatically rewritten. Buyer notification rows and saved listings are removed. Retention duration: TBD / policy decision required. |
| Contact / pilot interest | `ContactSubmission`, `WaitlistEntry` | These tables have no authenticated-user foreign key or verified ownership link. They are not included in self-service exports or automatically deleted at account closure. An operator must verify a request and review/remove the matching records manually. No automatic expiry is configured; retention duration: policy decision required. |
| Public business/content data | `CapacityListing`, listing `ImageField`, public manufacturer profile | Closure marks listings inactive/paused and anonymizes the Manufacturer profile; it does not delete listing rows or image objects. Cloudinary/provider deletion is a separate manual/provider-side task after checking historical references and the approved retention policy. |
| Security / operational records | `AuthRateLimitBucket`, Django sessions, logs and monitoring events | HMAC rate-limit digests are excluded from export. `prune_auth_throttles` removes expired buckets; schedule it daily. Account closure changes the password hash and logs out the current browser, invalidating other authenticated sessions when their next request checks the session hash. Physical session-row expiry/cleanup is separate. Log/Sentry retention is provider-managed and must be verified. |
| Backups / provider-held copies | Neon backups, Cloudinary media, Razorpay records, email delivery logs, Render logs, Sentry events, GitHub operational data | Application closure/export does not erase provider copies or historical backups. Retention, deletion and restore behavior must be checked with each provider. |

No fixed retention durations are set for Orders, historical Order requirements
snapshots, Quotation messages, Milestones, PaymentTransaction/WebhookEvent
records, Reviews, ContactSubmission, WaitlistEntry, listing media, or provider
logs/backups. Mark each as
**TBD / policy decision required** until the business and qualified counsel
approve a policy. Do not create an age-based cleanup command before that
decision.

## Account closure behavior

`/accounts/privacy/` requires authentication. Export is an authenticated,
user-scoped JSON response. Closure is a CSRF-protected POST and requires the
current password plus the typed word `CLOSE`; a GET cannot close an account.
The closure transaction locks the User row and rechecks credentials and
workflow eligibility before making changes. Workflow creation/quotation
response paths lock involved User rows in sorted primary-key order before
creating or accepting new obligations. Closure does not lock Order rows, which
avoids reversing the marketplace's Order-first milestone/payment lock order.
Manufacturer profile/listing writes, order messages, and reviews use the same
active-participant check so already-running requests cannot recreate those
records after closure commits.
Staff/superuser accounts use the support process.

Closure is blocked while the user participates in an Order that is not
Completed or Cancelled, a pending QuoteRequest, a quotation awaiting Buyer
response, or a Created payment transaction. No order cancellation, refund,
milestone change, payment release, or counterparty notification is performed.
If blocked, the user must resolve the workflow or contact support; operators
must not bypass this control by directly deleting the account.

On eligible closure:

- `User` remains to satisfy `PROTECT` references. Username/email are replaced
  by unique random `invalid.local` placeholders; first/last name, phone,
  last-login and consent metadata are cleared; `is_active` becomes false and
  the password becomes unusable. The original email is not encoded in the
  placeholder. A generic event ID is logged without user ID, email, phone or
  profile content.
- Manufacturer business/profile fields are anonymized, verification is
  cleared, and owned listings become inactive/paused. Historical listing rows
  and images remain. Direct public manufacturer profile access returns 404.
- Buyer-owned RFQ free text/location, delivery locations copied into that
  Buyer's Order snapshots, authored review comments, and Buyer milestone
  feedback are cleared. Historical Order `requirements` snapshots remain with
  completed/cancelled records as the commercial scope captured at transaction
  time. The closing user's order-message bodies are replaced with a generic
  marker. Manufacturer-authored `Quotation.message` text remains as historical
  marketplace negotiation/transaction context and is not automatically
  rewritten. Buyer `QuoteRequest.requirements` and `delivery_location` fields
  are cleared; they are distinct from the retained requirements snapshot on a
  completed/cancelled Order.
  Structured account/profile and delivery/contact fields are anonymized or
  cleared where implemented, but unstructured message/requirements text may
  contain user-entered personal details and is not automatically parsed or
  scrubbed. An exceptional privacy request involving this free text requires
  manual review. Retention duration remains TBD / policy decision required.
  Rows, timestamps, ratings, terms, and order references remain.
- Saved-listing and recipient notification rows are removed. Orders,
  Quotations, Milestones, PaymentTransaction, PaymentWebhookEvent and
  counterparty-authored transaction records are not deleted or rewritten.
- The current session is flushed. Replacing the password hash invalidates
  other Django authenticated sessions at their next authentication check;
  server-side session rows may remain until their configured expiry/cleanup.

The application does not directly delete Cloudinary objects. Anonymized
listing images may remain in provider storage and in backups until a separately
approved provider retention/deletion action. No recovery by the old email is
available after closure; Django password reset remains generic and excludes
inactive users.

## Export contents and exclusions

The export contains the requesting user's account/profile fields, owned
Manufacturer listings, Buyer-created quote requests, quotations authored or
received, participant orders and milestones, safe payment summaries, messages
authored by that user, reviews authored by that Buyer, saved listing titles,
and notification destination/read metadata.

Historical quotation messages are included only for quotations authored by
the requesting Manufacturer; a Buyer export includes the quotation record but
not the Manufacturer's message text. A Buyer export includes that Buyer's own
current QuoteRequest fields (which are blanked by eligible closure). An Order
requirements snapshot is included only for the requesting Buyer on that
Buyer-owned Order. Manufacturer exports omit Buyer-supplied Order details.
These are explicit owner/role allowlists; no separate counterparty
contact/profile fields are appended. User-entered free text is preserved as
written and may itself contain personal details. The export does not attempt
unreliable automatic text scrubbing.

The implementation uses explicit allowlists. It excludes password hashes,
sessions, CSRF values, reset tokens, HMAC throttle digests, `PaymentWebhookEvent`
payloads/signatures, provider credentials, provider transaction IDs, and
unnecessary counterparty emails, phones, addresses, or profile fields. It does
not include ContactSubmission or WaitlistEntry because neither has a verified
user foreign-key relationship; operators handle a separate request after
identity/ownership verification. Export is synchronous and currently expected
to fit the project's scale. Revisit asynchronous generation if data volume
grows materially.

## Support/contact/waitlist request procedure

1. Direct an authenticated user to the self-service export/closure page when
   possible. Never ask for a password by email or give an operator an
   impersonation path.
2. For an unauthenticated request, verify control of the relevant account or
   submitted contact address using the established support channel. Do not
   disclose whether another account/submission exists before verification.
3. Review active orders, requests, pending quotations, and payment attempts.
   Do not cancel, refund, edit milestone state, or erase counterpart records to
   make closure pass. Escalate unresolved obligations to the responsible
   business contact.
4. ContactSubmission/WaitlistEntry have no authenticated owner relation and
   no automated unsubscribe/delete workflow. Verify the request, locate only
   the matching email/role records, and remove or mark them according to the
   approved policy. The app currently has no outbound waitlist marketing
   automation; future pilot communication requests should be handled through
   support until an unsubscribe flow exists.
5. Record completion using a generic ticket/event reference and timestamp.
   Avoid copying request content, credentials, account IDs, or personal data
   into logs/screenshots. Confirm the outcome without claiming deletion from
   providers or backups.

## Provider and backup limits

Application-level anonymization does not delete data held by:

- Neon: database backups/PITR copies, branches, or access logs. Backup/PITR
  settings and retention require provider verification.
- Cloudinary: listing media, transformations, logs, or backups. No provider
  API was called by this phase.
- Razorpay: sandbox/payment records and provider-side event history. Payment
  identifiers and verified records are deliberately preserved in the app.
- Email provider: sent messages, bounce/audit logs, and queues.
- Render: application, build, and access logs.
- Sentry: event data and retention controls.
- GitHub: repository/workflow/security operational records.

Do not claim immediate erasure from backups, external providers, or logs. A
provider-by-provider retention/deletion review and the organization's RPO/RTO
and legal retention decisions remain outstanding launch operations work.
