# Visual Redesign V2 — Final QA

## Scope and repository state

- Audited on `main` from `f94b88d` (`Refine legal policy pages`). The preceding Visual V2 phase commits are present.
- No unrelated tracked changes were present at the start. `.kilo/` was already untracked; it was left untouched and excluded from the commit.
- Review captures and the isolated QA database were kept under the operating system temporary directory, outside the repository.
- The final pass made one scoped CSS fix and two E2E helper fixes: mobile marketplace filter/sort controls and listing-image upload controls now use 16px text; search/quote helpers match current routes and labels; and the order helper checks the actual order page structure. The viewport QA list now covers the remaining support and password-reset pages.

## Pages reviewed

Reviewed the public routes `/`, `/marketplace/`, listing detail, manufacturer profile, `/how-it-works/`, `/for-manufacturers/`, `/about/`, `/pricing-fees/`, `/trust-safety/`, `/faq/`, `/contact/`, `/grievance-redressal/`, `/privacy/`, `/terms/`, `/cookies/`, and `/refund-policy/`.

Reviewed account entry, login, both registration pages, password-reset request, sent, invalid-token confirmation, and completion pages. Reviewed Buyer dashboard, quote history, Buyer orders, saved listings, notifications, and order detail. Reviewed Manufacturer dashboard, listing management, create/edit listing, business-profile edit, notifications, and quotation workflow. Private routes redirect anonymous visitors to login as expected.

Public and account routes were loaded at 390px and 1440px in a browser audit. Responsive Playwright QA covers 320, 360, 390, 768, 1024, 1280, and 1440px. Buyer and Manufacturer authenticated views were also reviewed from disposable accounts created through the UI against a temporary local SQLite database.

## Findings and fixes

1. Marketplace filter and sort controls used 14–15px text at mobile widths. Scoped Visual V2 rules now set those controls to 16px at widths up to 760px. Listing image upload fields also use 16px text on mobile.
2. The E2E `acceptQuotationAndOpenOrder` helper expected the order reference to be the H1. The order page uses the listing title for its H1 and displays the order reference as metadata. The helper now checks the order URL, visible main H1, and visible `Order #…` reference.
3. The quote-flow helpers also contained stale expectations: search started from `/` with an obsolete button name, and quote submission expected an ID in a success panel where the current UI provides a history link. They now use `/marketplace/?q=…`, the current Request quote button, and the newest request reference in quote history.
4. No other verified site-wide visual defect required a code change. Layouts retain their context-specific density; no new design system or stylesheet was added.

## Consistency and legacy CSS

The shell, navigation, footer, headings, buttons, badges, forms, cards, empty states, and page gutters remain visually coherent across public and authenticated surfaces. The temporary screenshots showed that Buyer pages emphasize decisions and orders, while Manufacturer pages emphasize requests and capacity management, within the same Visual V2 shell.

`app.css` and `visual-v2.css` are loaded by the shared application shell. `trade-ledger-public.css` remains an additional stylesheet for the marketplace, listing detail, and manufacturer profile. Those pages still use its component layout rules, and Visual V2 provides the current public presentation. No project-wide legacy purge was justified. The only remaining visible old phrase found was the heading “Trade ledger / machine spec” on the noindex styleguide page; it is not shown on the redesigned product routes. Historical filenames and CSS classes remain internal implementation names.

Uncompressed stylesheet sizes at audit time:

- `app.css`: 239,785 bytes
- `visual-v2.css`: 169,244 bytes after the scoped final-pass additions
- `trade-ledger-public.css`: 15,181 bytes

The shared shell loads two main stylesheets, with the additional public marketplace stylesheet only on its three dependent surfaces. No duplicate load or obvious repeated JavaScript initialization was found. No Lighthouse package was installed, so no Lighthouse score is reported.

## Copy, product truth, and Sample safeguards

- A source scan found no stale public product copy using “Capacity register”, “Specification register”, “Manufacturing lanes”, “Supply rails”, or generic claims such as “seamless”, “revolutionary”, “unlock”, or “game-changing”.
- Payment and funding copy consistently describes demo/simulated states. It does not claim that the platform collects, holds, moves, or releases real money. Mentions of escrow are explicit denials of a live escrow service.
- Public verification wording ties the Verified badge to the current approved profile flag and distinguishes it from certification or a guarantee. KYC state alone is not presented as public verification.
- Sample listings are labelled and cannot request quotes; Sample profiles remain distinct from Verified profiles. Existing tests cover noindex and structured-data restrictions for Sample profiles/listings. Real listing/profile structured data and sitemap rules remain covered by focused tests.
- No FAQPage schema is added. Existing page metadata and indexing strategy were not changed.

## Navigation, links, forms, and images

- The browser audit loaded 64 public/account/private-route visits with HTTP 200 responses after expected redirects. It found 35 unique internal links from the reviewed pages; none returned an error.
- Anonymous and authenticated navigation were reviewed. Desktop destinations and mobile menu behavior remain consistent; the expected marketplace route is `/marketplace/`.
- Login, registration, contact, quote request, quotation, listing, profile, password-reset, order-message, and consent controls were inspected in their current templates or browser flow. Labels, error/help associations, password controls, upload presentation, and semantic button/link behavior remain in place. Mobile form input text was 16px; the marketplace filters and file inputs were corrected in this pass.
- No broken local images, images wider than the viewport, failed local asset requests, or browser console errors were found in the route audit. Missing listing imagery uses the existing labelled fallback; no stock or fabricated images were added.
- The footer links reach the intended public/support/legal routes. No blank configured contact details were exposed.

## Responsive, accessibility, cookie, and SEO results

- Responsive viewport QA checks page overflow, clipped headings/buttons, image width/load, footer overlap, and mobile marketplace control size across 320, 360, 390, 768, 1024, 1280, and 1440px.
- The mobile navigation, skip link, reduced-motion behavior, FAQ disclosures, filters, and legal contents disclosure have keyboard E2E coverage. Page audits found one H1 per reviewed route. Semantic form labels, statuses with text, and focus styles remain present.
- Axe is not installed in the project; no axe scan was run. Contrast received a visual review using the existing Visual V2 palette, not an automated WCAG audit.
- The cookie panel was reviewed at 320/360/390px on the homepage, marketplace, login, Buyer/Manufacturer registration, Buyer dashboard, order, Contact, and Cookie Policy. It can overlap lower content until a choice is made, but its controls remain visible and usable, it is non-modal, and dismissing it restores the page. Consent behavior was not changed.
- Public pages returned unique titles, descriptions, canonicals, Open Graph, and Twitter metadata in the local browser audit. Local E2E settings run with debug indexing disabled, so responses included `noindex`; this is expected for the local QA environment. Existing tests cover production indexing settings, sitemap inclusion/exclusion, canonical URLs, Sample noindex behavior, and structured data. Confirm deployment `ALLOW_INDEXING` settings before launch.

## Core workflow

Using a temporary local QA database and disposable UI-created accounts, the browser flow completed: Buyer and Manufacturer registration, Manufacturer listing creation, Buyer marketplace discovery and quote request, Manufacturer quotation, Buyer acceptance and order creation, messages from both roles, simulated milestone funding, Manufacturer start/completion, and Buyer approval/release. The Manufacturer verification flag was enabled only in that isolated QA database to make the listing quote-eligible; this did not change application code or production data. A second quote/order cycle verified the corrected E2E helper.

Existing Django tests cover role access, quotation/order behavior, milestone permissions, Sample restrictions, auth, and profile/listing safeguards. Playwright credential-gated production smoke tests remain skipped when their QA credentials are absent; the local browser flow above used disposable non-production data.

## Tests and checks

Final results:

- `python manage.py check`: passed
- `python manage.py makemigrations --check --dry-run`: no changes detected
- Focused local browser workflow and corrected quote/order helpers: passed
- `python manage.py test`: 198 passed
- `npx playwright test`: 28 passed, 11 credential-gated skips, 0 failed
- `git diff --check`: passed

## Known limitations

- Contact-submission retention period is unspecified.
- Governing law and formal dispute-resolution policy are undefined.
- Direct Buyer–Manufacturer refund/cancellation terms are not specified by the platform.
- A detailed verification checklist is not published.
- A future fee schedule is not defined.
- The cookie panel overlays lower content until the user makes a choice.
- Some long registration, listing, and legal pages naturally require scrolling on mobile.
- Credential-gated production E2E tests skip without QA credentials; the local disposable-account flow was exercised separately.

## Recommendation

The Visual V2 implementation is coherent and the final browser QA found no blocking UI regression. The UI work is ready for a production release gate, subject to the product owner confirming the unresolved policy items above and deployment confirming `ALLOW_INDEXING` is configured as intended. No deployment was performed.
