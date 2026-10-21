# Visual Redesign V2: Phase 0 Audit

## Scope and baseline

This audit records the implementation at commit `7644c8c` before Phase 0 CSS changes. The working branch was `main`; the requested commit was `HEAD`. No tracked files were modified at the start of the audit. `.kilo/` was the only untracked path and was left untouched.

The initial screenshots were captured at 390px and 1440px for the landing page, marketplace, a sample listing detail, login, buyer dashboard, and manufacturer dashboard. The public visual QA suite rejects analytics before capturing its page screenshots, so a separate first-visit 390px capture was used to inspect the cookie panel. Dashboard captures used a temporary local buyer account and the existing demo manufacturer account. These screenshots are temporary QA evidence and are not part of the repository.

## Global shell

- **Header:** The logo is visible at desktop and mobile widths. Desktop navigation presents Marketplace, How it works, For manufacturers, Resources, login/account state, and one primary anonymous `Get started` CTA. Its named route resolves to `/accounts/get-started/`. Authenticated buyer and manufacturer links remain in role-specific template branches. The mobile trigger is a real button with `aria-expanded`, `aria-controls`, and an accessible label; Escape and navigation-link activation close the menu. The menu is hidden from keyboard interaction while closed through `inert`.
- **Mobile menu:** At 390px it fits without horizontal overflow. Opening by the trigger exposes a single-column menu. There is no outside-click close handler, but link activation, Escape, and returning to desktop width close it predictably.
- **Branding:** The header and footer wordmarks are readable in captures. The mobile header mark is smaller but not hidden.
- **Footer:** The navy footer is consistent across the sampled routes and uses only configured legal identity/contact values when available. Its four link groups stack into a long but readable mobile footer. No missing company details are fabricated.
- **Page width and breakpoints:** The base container is 1180px in `app.css`, `.container` is overridden to 1200px by Visual V2, while several public blocks separately use 1200px `min()` widths. Landing content has a 48px desktop gutter and 36px mobile gutter; other pages use 24px base gutters, with marketplace sections using 36px at mobile. This works at 390px but is more than one container/gutter system.
- **CSS loading:** `base.html` loads `app.css`, then each page's optional `extra_css`, and finally `visual-v2.css`. `app.css` contains repeated/overlapping declarations from earlier design iterations; Visual V2 currently wins through source order for only the selectors it explicitly covers. This creates real legacy/new cascade overlap, although many old declarations remain necessary for authenticated pages.

## Typography

- **Landing:** The hero H1 is prominent and the section headings form a clear hierarchy. Body text and marketplace descriptions remain readable at 390px. Muted text is generally legible against the pale background.
- **Marketplace and listing detail:** Marketplace H1/H2 sizing is consistent with the new navy/teal treatment. Listing technical values still use the older specification-sheet typography, including small uppercase labels and monospaced values.
- **Login/account:** Login retains the older split-panel cream/green styling and serif display type while the shared header, buttons, and footer use the new navy/teal system. At 390px, this is the clearest cross-page typography and color collision.
- **Responsive sizing:** Landing H1 clamps to 34–38px on mobile, marketplace H1 to 34px, and the listing detail H1 inherits the older trade-ledger rules. The page QA spec found no heading clipping or oversized H1 at 390px and 1440px.
- **Weights and muted text:** Visual V2 uses 650–700 weights for controls and headings. Some old templates still apply heavier weights and multiple muted color variables; this makes non-redesigned dashboard and account pages less uniform.

## Spacing and shape

- Landing sections have generous desktop spacing and more compact mobile spacing. The mobile page is long but the hero and first search actions are visible early.
- Marketplace desktop content has a wide two-column filter/results layout; mobile turns filters into a disclosure and stacks listing terms below each listing. The mobile listing cards are dense but scannable.
- Dashboard captures show stacked content sections and many empty-state panels. At 390px their small labels and large number of sections create a long scroll; those dashboard layouts have not been visually redesigned.
- Visual V2 uses 8–12px component radii, while `app.css` retains 0–4px, 6px, 8px, 10px, 12px, 16px, and 20px radii in active component rules. This is a real inconsistency, though not every older compact control conflicts with the new card surfaces.
- A single 1200px container token is appropriate for the new shared public shell; legacy 1180px and separately hard-coded widths remain in `app.css` and page selectors.

## Buttons and forms

- Primary buttons use navy on the landing, marketplace, and shared header CTA; secondary buttons are white with a muted border. The visible CTA hierarchy is clear on those pages. Text actions use teal links.
- Core buttons have competing 42px, 44px, and 48px minimum heights in `app.css` and `visual-v2.css`; compact logout buttons intentionally use a smaller size. Existing focus styles are present, but they vary between amber, teal, and legacy gold.
- Login and waitlist inputs are at least 16px on mobile. The global form base still uses several border, radius, focus, and weight treatments. Checkbox/radio controls have native semantics and labels in the inspected login and waitlist forms.
- The dashboard and account pages use the shared button/form class names, so a small global foundation is safer than page-specific restyling.

## Cards, badges, alerts, empty states, breadcrumbs, and pagination

- Marketplace listing rows are a distinct active component (`listing-spec-row`) rather than generic cards. They align the listing fallback visual, product details, and commercial facts, and should remain a distinct layout.
- Landing audience cards, listing cards, filter panels, auth panels, and dashboard record/summary cards have separate markup and CSS. There is not one universal card system; the landing and marketplace redesign uses a coherent subset while dashboards retain the older raised-card treatment.
- `Sample`, `Verified`, availability, and status badges are driven by existing classes and business state. Their appearances should be standardized without moving or changing the conditions that render them.
- Message/alert styles are scattered among `.message`, `.alert`, sample notices, and status panels. Empty states are separately styled as `.empty-panel`, `.empty-state`, and `.marketplace-empty-state`.
- Breadcrumb and pagination markup is currently styled in the trade-ledger/public CSS and app CSS. Pagination URLs and logic are already rendered by templates and need no behavioral change.

## Landing page

- **Strongest areas:** The hero quickly identifies manufacturers with spare capacity and small-batch orders, provides an immediate search field, and pairs it with a marketplace preview. The audience choice, workflow, listing examples, and early-access state follow in a sensible order.
- **Weakest areas:** The page is exceptionally long on mobile due to the full set of educational, listing, trust, waitlist, and FAQ sections. At 390px each section remains readable, but the accumulated scroll is substantial. The cookie panel can obscure the current viewport while the user is reading.
- **Hierarchy/density:** The hero has a clear H1 and search action; later sections use a repeated pale-panel/card rhythm. Density is moderate on desktop and taller on mobile.
- **Five-second communication:** Yes. The headline, lede, search prompt, and marketplace preview communicate the product within the first screen.

## Marketplace

- **Search and filters:** Search is visually separate from filters. At mobile widths, filters collapse into a “Filters and sort” disclosure; the result count and sort context remain in the result heading.
- **Result hierarchy:** Result count, sample notice, listing title, manufacturer, location, process, price, MOQ, lead time, and capacity are visually distinguishable.
- **Desktop density:** The 1440px two-column layout makes good use of width, though listing rows are broad with substantial gaps.
- **Mobile density:** One listing per row keeps content legible. The technical facts move below each listing, extending page height; pagination remains visible and usable.
- **Filter UX:** The disclosure works as a native summary/details control. Search and filter controls use native form elements and mobile-sized text. No pagination behavior change is needed.

## Legacy visual leakage and active usage

- `trade-ledger-public.css` is actively loaded by `home.html`, `listing_detail.html`, and `manufacturer_profile.html`. Its selectors are used by the current marketplace, listing detail, and manufacturer-profile templates. It is not safe to delete wholesale.
- `marketplace_trade_ledger.html` is the active marketplace include; its filename is historical, while the visible rows are the revised listing-spec layout. `listing_detail.html` actively includes `listing_detail_trade_sheet.html`; the old editorial block below it is inside a Django comment and is not active.
- The listing detail screenshot still has specification-sheet remnants: uppercase field labels, compact technical facts, and a commercial terms panel. Some are useful data hierarchy; the monospaced value styling and small labels are the clearest old-style remnants.
- No “capacity register” wording was found in current visible public copy. “Trade ledger” remains in filenames and CSS naming, not user-facing text in the inspected screens. These backend/template identifiers remain unchanged.
- `app.css` contains older warm-paper and serif account styles, alternate token palettes, repeated header/button/form rules, and multiple responsive cookie rules. The login screenshot confirms that the warm cream panel remains active. Several trade-ledger rules remain active on the listing detail and profile pages.
- Visual V2 currently contains no `!important` declarations other than the reduced-motion override. `app.css` has intentional `!important` rules for hidden honeypot fields and isolated legacy overrides; these need usage checks before removal.
- Inline styles in landing and listing templates are uncommon; a source scan did not find meaningful style attributes in the audited templates. Inline scripts in `base.html` are functional consent, navigation, motion, and form behavior and are outside this visual CSS scope.

## Initial screenshot review

- **Landing, 390px and 1440px:** Strong hero and clear product message. Mobile content fits without overflow; the page is long but sections stack consistently. Desktop whitespace is generous and purposeful.
- **Marketplace, 390px and 1440px:** The result structure remains readable and the filter layout adapts cleanly. Desktop listing rows have ample horizontal space; mobile facts are pushed below the title block, increasing vertical density.
- **Listing detail, 390px and 1440px:** The fallback graphic works at both sizes and commercial terms are easy to scan. Desktop composition leaves a broad empty image field beneath the sample illustration; technical metadata retains its older compact specification-sheet look.
- **Login, 390px and 1440px:** No overflow, but the account form's cream surface, green-black story panel, and serif display heading visibly diverge from the new global palette. The mobile form and footer remain usable.
- **Buyer dashboard, 390px and 1440px:** The cards stack without overflow. The 390px view is very long, with small metadata and many empty panels. The 1440px view is balanced but still uses the older faint grid hero and shadow-heavy dashboard cards.
- **Manufacturer dashboard, 390px and 1440px:** No overflow. Mobile action and quote cards are long and compact; desktop quote-request cards are dense and have a separate older component system. This is not a regression from Visual V2 because it is outside the redesign scope, but the shared style foundation can reduce button/control inconsistencies.
- **First-visit cookie panel:** At 390×844 the fixed bottom panel sits over the page and the three actions consume roughly 125px. The explanatory paragraph is hidden by existing mobile CSS. The primary hero search buttons remain above it in the initial view, but the panel can cover lower content, forms, or controls after scrolling. This is materially intrusive, particularly on short screens.
- **Width checks:** The existing visual QA sweep passed at 390px and 1440px for the public routes and listing detail. It did not include dashboard captures without QA credentials; temporary local QA accounts were then supplied, and both dashboard views passed at those widths. The full 320/360/768/1024/1280 sweep remains part of Phase 0 verification.

## Phase 0 stabilization

This section records the stabilization made after reviewing the baseline screenshots.

### Changes made

The shared foundation was consolidated in the existing `visual-v2.css`; no parallel stylesheet was added.

- Added the requested primary, accent, background, surface, border, text, muted, warning, success, and danger tokens, plus container, spacing, radius, shadow, and transition values.
- Standardized common button variants and focus/disabled states, form-control sizing and focus, badge shapes/variants, alert colors, card surfaces, breadcrumbs, and pagination presentation. Compact controls keep their existing compact purpose.
- Brought the account split panel into the navy/teal surface language, set a single-column mobile grid, and retained the existing header and role-specific navigation logic.
- Reworked the first-visit cookie panel's mobile presentation: the full purpose and consent meaning remain visible, all three choices remain available, mobile targets are 48px high, and safe-area spacing is respected. At 320px, small hero spacing adjustments keep the primary search button above the panel.
- Shortened the cookie explanation while retaining that necessary cookies support login, CSRF protection, and the saved choice, and that optional analytics help improve the marketplace while remaining off until allowed. Consent categories, actions, analytics loading, storage, and privacy behavior were not changed.
- No models, migrations, URLs, authentication logic, quote/order/milestone/messaging/KYC/verification rules, contact/waitlist backends, sitemap, sample restrictions, or database behavior were changed. `.kilo/` was not read or modified.

### Before/after comparison

| Surface | Hierarchy clearer? | Spacing more consistent? | Visually calmer? | Mobile better? | Existing page regressions? | One coherent design language? |
| --- | --- | --- | --- | --- | --- | --- |
| Landing | Same clear hero hierarchy; shared controls and sample badges are more consistent. | Yes at common controls; existing section spacing is preserved. | Yes; the V2 palette remains steady. | Yes at 320px: the primary search action stays above the cookie panel. 360/390 layouts retain their prior structure. | No. | Yes for the public shell. |
| Marketplace | Slightly clearer badge and button treatment; result hierarchy is unchanged. | Yes for control heights, card radius, and pagination. | Yes; neutral surfaces and restrained shadows remain. | Yes; seven-width sweep showed no overflow, and the mobile filter/listing layout is unchanged. | No. | Yes for public search/results. |
| Listing detail | Commercial terms and sample state are easier to distinguish; specification hierarchy remains as before. | Yes for shared surfaces and controls. | Yes, with calmer sample badges and a common surface treatment. | Yes; fallback art, facts, and similar-listing rows remain readable with no overflow. | No. | Mostly; active specification-sheet typography remains a legacy visual. |
| Login | Yes; the form now reads as part of the same account/public interface. | Yes; inputs and buttons have consistent sizing. | Yes; cream and serif styling is gone in favor of white and navy/teal. | Yes; the auth panel stacks within the viewport and controls remain usable. | No. | Yes for the shared shell and account surface. |
| Buyer dashboard | No content hierarchy change; shared controls are more consistent. | Yes for common buttons, fields, and card edges. | Slightly; existing panels remain visually quiet. | No layout redesign; 320/360/390/768/1024/1280/1440 passed without overflow. | No. | Partly; its older dashboard presentation remains. |
| Manufacturer dashboard | No content hierarchy change; status badges and shared controls are more consistent. | Yes for common buttons and surfaces. | Slightly; the existing dashboard layout is preserved. | No layout redesign; all seven responsive widths passed without overflow. | No. | Partly; dense quote cards remain an older component system. |

The separate first-visit screenshots show the cookie panel at 320×700, 360×800, and 390×844. It does not cover the header or primary hero search action. It still covers some lower content in the initial viewport, including the secondary “List your capacity” action at 390px; the page scrolls normally and users can bring controls above the fixed panel. On the 390px login page it overlaps the lower form area until the user scrolls. The panel is now about 150–162px high, with all explanatory copy and choices visible. This is less intrusive than the baseline panel, which hid its explanation and used two action rows.

At 1440px the cookie panel remains fixed at the bottom left and can cover lower first-viewport content. It does not cover the header or primary landing search action. The consent decision remains explicit.

### Before/after comparison

All six requested surfaces were captured at 390px and 1440px after the foundation changes. Landing, marketplace, listing-detail, login, buyer-dashboard, and manufacturer-dashboard screenshots were opened and reviewed. The dedicated cookie captures were also reviewed at 320px, 360px, and 390px; the login first-visit capture was checked at 390px. Screenshots were held under the system temporary directory and are not repository files.

The homepage and marketplace do not receive a new layout in this phase. Their main composition is unchanged; control and badge consistency improved, and the only page-specific spacing tweak is the narrow 320–360px landing hero adjustment needed to keep the primary search button clear of the cookie panel.

### Verification

### Accessibility and responsive checks

- The header remains semantic: a button toggles the navigation, the menu uses links, `aria-expanded` and `aria-controls` remain in place, and Escape/link activation close the mobile menu. The keyboard-navigation E2E case passes.
- Visible focus rings use the accent color. Primary white-on-navy and accent/muted text on white meet WCAG AA contrast based on the token colors; the gold warning token is used as a surface accent with dark text, not small text on white.
- The inspected landing/login/listing pages have one H1 followed by section H2s and nested H3s. Form fields keep labels, submit actions remain buttons, navigation remains links, and no clickable divs were introduced.
- Brand images inside named links use empty alt text; the listing fallback geometry is explicitly hidden from assistive technology. Reduced-motion overrides remain in place and the E2E reduced-motion check passes.
- Responsive visual tests check horizontal overflow and missing/clipped headings. The full sweep passed at 320, 360, 390, 768, 1024, 1280, and 1440px, including both dashboards. Additional final checks at 320, 360, 390, and 1440px passed after the narrow-screen cookie refinement.

### Verification

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: `No changes detected`.
- `python manage.py test`: 173 tests passed.
- Full `npx playwright test`: 34 passed, 4 environment-gated skips. The local dashboard accounts were supplied for the visual sweep; the four skips are unrelated production credential/commerce gates.
- Final focused keyboard/consent run: 8 passed. Final 320px visual check: 2 passed (public pages and dashboards). The 360px, 390px, and 1440px public/dashboard visual checks also passed.
- `git diff --check`: passed.

### Remaining visual problems

- `app.css` remains a large accumulated stylesheet with repeated token sets and older responsive declarations. Those rules still support live non-redesigned surfaces, so they were not broadly deleted in this audit.
- `trade-ledger-public.css` remains active on the marketplace, listing detail, and manufacturer profile. The listing detail still shows small uppercase specification labels and monospaced values; these are the confirmed specification-sheet remnants.
- The dashboards remain long, especially on mobile. Their data density and separate record-card layouts are outside this foundation pass.
- The fixed consent panel continues to cover lower viewport content while a choice is pending; it no longer covers the primary search action at tested mobile widths, and the full explanation and actions remain visible.
