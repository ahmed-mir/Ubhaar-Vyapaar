# Ubhaar-Vyapaar Legal and Privacy Risk Review

Date: 2026-10-11
Scope: code/product review for the current Ubhaar-Vyapaar prototype.

This document is not legal advice and does not conclude that the application is
compliant with the Digital Personal Data Protection Act, 2023, DPDP Rules 2025,
Information Technology Act / IT Rules, Consumer Protection Act, E-Commerce Rules,
or any other law. It records code-observed risks and recommended follow-up.

Reference material for professional review:
- MeitY, Digital Personal Data Protection Act, 2023:
  https://www.meity.gov.in/writereaddata/files/Digital%20Personal%20Data%20Protection%20Act%202023.pdf
- MeitY, Digital Personal Data Protection Rules 2025:
  https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa?pageTitle=Digital-Personal-Data-Protection-Rules-2025

## Data Inventory Summary

- Account data: username, email, optional phone, role, password hash, consent timestamps and policy versions.
- Manufacturer profile: business name, description, city, state, verification flag, KYC status.
- Listings: category, title, description, machine type, materials, technical capabilities, MOQ, prices, production days, capacity, cluster, status, public listing image.
- Buyer workflows: saved listings, quote quantity, requirements, delivery location.
- Commercial workflows: quotations, accepted quotation terms, orders, JSON specification snapshots, simulated milestone funding/release states, buyer feedback.
- Communications: order messages, notifications, reviews and ratings.
- Cookies/storage: Django session and CSRF cookies; no code-observed analytics, marketing cookies, localStorage, or sessionStorage.
- Third parties: Cloudinary for public listing images in production; SMTP email provider, with Brevo documented as production SMTP option; WhiteNoise for static files. No code-observed Google Fonts, icon CDNs, analytics scripts, embedded maps, YouTube/Vimeo, chat widgets, social widgets, or CSS/JS CDN dependencies.

## Risk Register

### HIGH - Missing configured legal/operator contact details

- Issue: Public legal pages cannot identify a real legal entity, address, grievance officer, or confirmed privacy contact because the codebase does not contain those facts.
- Why it may matter: Privacy notices, user rights requests, platform disputes, and consumer/intermediary processes may require clear contact channels depending on the legal role and deployment model.
- Current implementation: Settings-backed `LEGAL_ENTITY_NAME`, `LEGAL_CONTACT_EMAIL`, and `LEGAL_CONTACT_LABEL` exist. Public pages show that details are not configured if missing.
- Recommended action: Deployment owner must configure real, reviewed contact/entity information before production use.
- Code change made: Yes.
- Professional legal review required: Yes.

### HIGH - No formal data retention/deletion workflow

- Issue: Accounts, messages, notifications, orders, reviews, listings, and media uploads may be retained indefinitely.
- Why it may matter: Data minimization and storage-limitation expectations may require defined retention periods, especially for inactive accounts and old communications.
- Current implementation: Timestamps exist on many records, but no retention schedule or deletion/anonymisation workflow exists.
- Recommended action: Define retention categories for account records, business/order records, messages, notifications, listing images, inactive accounts, and logs. Avoid automatic deletion of critical business/order records until legal and operational requirements are defined.
- Code change made: Partial; policy pages disclose retention status. No destructive cleanup added.
- Professional legal review required: Yes.

### HIGH - Simulated payments could be misunderstood

- Issue: Milestone funding/release states exist and include monetary amounts, but no real payment processing or escrow exists.
- Why it may matter: Ambiguous language could imply regulated financial services, escrow, or real money movement.
- Current implementation: Order views already used demo language. Phase 12 terms and refund policy explicitly state that no real payments, money movement, or escrow are provided.
- Recommended action: Continue reviewing all payment-like UI before adding real payment providers.
- Code change made: Yes.
- Professional legal review required: Yes before any real payment or escrow feature.

### MEDIUM - Registration consent previously not explicit or recorded

- Issue: Account creation did not require explicit Terms/Privacy acknowledgement or store policy version/timestamp.
- Why it may matter: Notice and consent evidence may be relevant for privacy accountability.
- Current implementation: Registration now requires a server-side checkbox and stores terms/privacy timestamps and policy versions.
- Recommended action: Review final wording and versioning process with counsel.
- Code change made: Yes.
- Professional legal review required: Yes for wording and retention period.

### MEDIUM - Manufacturer verification/KYC status lacks public process detail

- Issue: The model tracks KYC status but does not upload KYC documents. The verification decision process is not documented in detail.
- Why it may matter: Users may need to understand what verification means and what data may be requested later.
- Current implementation: No KYC document fields exist. Status only is stored.
- Recommended action: Define verification criteria and future document handling before collecting private documents. Do not use public Cloudinary storage for private KYC files.
- Code change made: Policy clarifies no KYC document upload currently exists.
- Professional legal review required: Yes.

### MEDIUM - User deletion/correction workflow is manual

- Issue: Users can change passwords, and manufacturers can edit business profiles, but there is no safe self-service account deletion workflow.
- Why it may matter: User rights and dispute handling may require a defined process.
- Current implementation: Privacy page explains correction/deletion request pathway and notes missing configured contact if absent.
- Recommended action: Build an admin-reviewed deletion/anonymisation workflow that preserves legally/business-critical order records where required.
- Code change made: Partial; public instructions added.
- Professional legal review required: Yes.

### MEDIUM - Third-party processing requires provider review

- Issue: Cloudinary and SMTP/Brevo may process uploaded listing images, email addresses, and email contents.
- Why it may matter: Vendor contracts, regions, retention, subprocessors, and security terms may need review.
- Current implementation: Cloudinary is used only for public listing images; SMTP is configurable; no analytics/marketing providers are loaded.
- Recommended action: Review Cloudinary and email-provider agreements, regions, retention, and access controls before production.
- Code change made: Policy pages disclose provider usage.
- Professional legal review required: Yes.

### MEDIUM - Marketplace/intermediary and e-commerce role uncertainty

- Issue: Ubhaar-Vyapaar hosts manufacturer listings, buyer/manufacturer communications, and reviews, but its precise legal role is not defined.
- Why it may matter: Depending on launch model, marketplace/intermediary, e-commerce, takedown, grievance, seller disclosure, consumer-protection, and recordkeeping expectations may apply.
- Current implementation: Terms describe roles and prohibited conduct but do not create final legal process language.
- Recommended action: Determine whether the service acts as marketplace, intermediary, lead-generation tool, SaaS workflow tool, or another role before production terms.
- Code change made: Draft terms and policy pages added.
- Professional legal review required: Yes.

### LOW - No optional cookies or trackers currently found

- Issue: A consent manager could be misleading if it implies optional tracking exists.
- Why it may matter: Deceptive banners can reduce transparency.
- Current implementation: No cookie banner was added. Cookie policy classifies current Django session and CSRF cookies as strictly necessary.
- Recommended action: If analytics/marketing are added, implement category-based consent before loading them.
- Code change made: Yes.
- Professional legal review required: Low, unless optional tracking is added.

### LOW - Accessibility best-practice review remains incomplete

- Issue: The app has semantic labels, skip link, focus-visible styles, and responsive UI, but no formal WCAG audit.
- Why it may matter: Accessibility expectations may apply depending on users, customers, or public-sector context.
- Current implementation: Phase 12 did not perform a full accessibility audit.
- Recommended action: Run keyboard, screen-reader, contrast, and form-error audits before production.
- Code change made: No dedicated accessibility change in Phase 12 beyond accessible consent field behavior.
- Professional legal review required: Maybe; technical accessibility audit also recommended.

## Recommended Retention Categories

- Account identity and consent records: retain while account exists and for a reviewed post-closure period.
- Manufacturer profile and verification status: retain while business profile/listings are active and for a reviewed audit period.
- Listings and listing images: retain while active or needed for order/quote history; define cleanup for abandoned/inactive listings.
- Quote requests and quotations: retain with related order/business records; do not auto-delete without business/legal review.
- Orders and milestones: treat as critical business records; avoid automatic deletion until retention obligations are defined.
- Messages: retain with order history unless deletion/anonymisation workflow is approved.
- Notifications: candidates for low-risk cleanup after a defined period, but no automatic cleanup was implemented in this phase.
- Reviews: retain while manufacturer reputation/history is displayed; define removal/moderation policy.
- Logs: hosting/server logs are outside the Django models; configure platform retention separately.
- Media uploads: public listing images only; define cleanup when listings are deleted or made inactive.
