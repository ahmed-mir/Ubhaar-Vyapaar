# Modern UI route audit (Phase 7A)

Scope: shared visual foundation only. The shared brand, typography, containers, controls, navigation, and shell are addressed in 7A. Route-level composition and data hierarchy remain queued for Phase 7B. Protected screens require QA credentials for screenshot review; no credentials were present in this workspace.

## Public

| Page / route | Current visual concerns | Target pattern | Phase |
|---|---|---|---|
| Homepage `/` | Polished Visual V2 is the reference; shared token drift can make global controls feel unrelated. | Preserve current composition; align shared tokens and controls. | 7A foundation; no route redesign |
| Marketplace `/marketplace/` | Dense filters and listing rows have separate public styling; accent and control tokens drift from product styles. | Search and filter rail plus efficient listing rows; compact status labels. | 7A shared; 7B marketplace |
| Listing detail `/listings/<id>/` | Editorial trade sheet contains a distinct component set and page-specific spacing. | Clear item summary, capability facts, quote action, then supporting detail. | 7A shared; 7B listing |
| Manufacturer profile `/manufacturers/<id>/` | Trade ledger/profile components use separate width and typography rules. | Trust and capability summary followed by operational facts and listings. | 7A shared; 7B profile |
| About `/about/` | Informational template family needs consistent prose width and heading rhythm. | Public page header and readable 720–800px text column. | 7A shared; 7B informational |
| How it works `/how-it-works/` | Step/story content has a specialized layout and motion styling. | Short intro with clear, sequential workflow sections. | 7A shared; 7B informational |
| For manufacturers `/for-manufacturers/` | Conversion page uses marketing-specific sections and card patterns. | Public page header, practical benefits, accurate next action. | 7A shared; 7B informational |
| Pricing & fees `/pricing-fees/` | Commercial facts need consistency with compact public content patterns. | Transparent fee sections, readable tables/lists, no promotional inflation. | 7A shared; 7B informational |
| Trust & safety `/trust-safety/` | Long trust content shares components with general pages but needs clearer hierarchy. | Compact public header and scannable trust sections. | 7A shared; 7B informational |
| FAQ `/faq/` | Long disclosure list needs consistent spacing and accessible controls. | Grouped questions with concise answers and clear section headings. | 7A shared; 7B support |
| Contact `/contact/` | Form fields and informational copy need a clear common form width. | Page intro, bounded form, field-level errors, compact success/error messages. | 7A shared; 7B support |
| Grievance redressal `/grievance-redressal/` | Long contact/legal details need deliberate prose width. | Readable legal/content column with clear contact route. | 7A shared; 7B support |
| Help `/help/` | Support content is a general public template with no dedicated route-level audit yet. | Compact support index with clearly grouped destinations. | 7A shared; 7B support |
| Privacy `/privacy/` | Legal prose is subject to shared generic page widths. | 720–800px legal column and structured headings. | 7A shared; 7B legal |
| Terms `/terms/` | Legal prose is subject to shared generic page widths. | 720–800px legal column and structured headings. | 7A shared; 7B legal |
| Cookies `/cookies/` | Legal prose is subject to shared generic page widths. | 720–800px legal column and structured headings. | 7A shared; 7B legal |
| Refund policy `/refund-policy/` | Legal and payment wording needs readable, careful section hierarchy. | 720–800px legal column; preserve simulated-payment language. | 7A shared; 7B legal |
| Shared public content `/...` | `public_content_page.html` powers additional informational copy pages; content route list depends on configured records. | Reuse public header and constrained prose rhythm. | 7A shared; 7B informational/legal |
| Style guide `/styleguide/` | Internal component reference; currently reflects accumulated styles rather than a single source of truth. | Refresh examples to reference canonical tokens after route phases settle. | 7A foundation; 7B documentation |

## Auth

| Page / route | Current visual concerns | Target pattern | Phase |
|---|---|---|---|
| Get started `/accounts/get-started/` | Auth chooser shares account components but needs compact choice hierarchy. | Focused auth page header and clear role choices. | 7A shared; 7B auth |
| Buyer registration `/accounts/register/` | Long form can feel dense; shared field rhythm and mobile sizing need consistency. | Bounded form, clear labels, field-level errors. | 7A shared; 7B auth |
| Manufacturer registration `/accounts/register/manufacturer/` | Long profile setup form uses the same mixed legacy form rules. | Bounded, grouped form with practical labels and one primary submit. | 7A shared; 7B auth |
| Login `/accounts/login/` | Auth template has separate split-panel styling and old typography overrides. | Compact sign-in form with predictable page header and support links. | 7A shared; 7B auth |
| Password reset `/accounts/password/reset/` | Shared control styling; route-specific explanation and error treatment need review. | Bounded reset form and compact confirmation messaging. | 7A shared; 7B auth |
| Password reset sent `/accounts/password/reset/done/` | Confirmation page has a low-content state. | Compact confirmation with one useful next step. | 7A shared; 7B auth |
| Password reset confirmation `/accounts/password/reset/<uid>/<token>/` | Form state can vary for valid/expired tokens. | Bounded password form or concise expired-link state. | 7A shared; 7B auth |
| Password reset complete `/accounts/password/reset/complete/` | Low-content completion state. | Compact completion message and login action. | 7A shared; 7B auth |
| Password change `/accounts/password/change/` | Authenticated account form shares legacy field styling. | Product page header and bounded form. | 7A shared; 7B account |
| Password change done `/accounts/password/change/done/` | Low-content completion state. | Compact confirmation with account navigation. | 7A shared; 7B account |
| Logout `/accounts/logout/` | POST action; no independent content page. | Keep current route and navigation behavior. | No visual page |

## Buyer

| Page / route | Current visual concerns | Target pattern | Phase |
|---|---|---|---|
| Dashboard `/buyer/dashboard/` | Operational sections inherit generic cards and the shell; role-specific density needs page review. | Compact title/context, priority action, then grouped activity/records. | 7A shared; 7B buyer |
| Quote request `/listings/<id>/request-quote/` | Long form needs bounded width and clear sample restrictions. | Item context then short quote form; preserve sample quote restrictions. | 7A shared; 7B buyer |
| Quote requests `/my-quote-requests/` | Multiple request states need efficient comparison and status hierarchy. | Structured rows/sections with concise status treatment. | 7A shared; 7B buyer |
| Buyer orders `/buyer/orders/` | Operational records need clearer data density than generic cards. | Responsive order rows with status and next action. | 7A shared; 7B buyer |
| Order detail `/orders/<id>/` | Detail page combines milestones, messaging, and payment states. | Compact order summary, explicit milestone sequence, readable message area. | 7A shared; 7B buyer |
| Review order `/orders/<id>/review/` | Rating form needs clear grouping and validation. | Bounded form with clear labels and field-level feedback. | 7A shared; 7B buyer |
| Saved listings `/saved-listings/` | Listing objects need efficient scanning and useful empty state. | Listing rows/cards only for the listing object; compact empty state. | 7A shared; 7B buyer |
| Notifications `/notifications/` | Activity list needs readable time/context hierarchy. | Grouped notification rows with compact read/unread distinction. | 7A shared; 7B buyer |
| Open notification `/notifications/<id>/open/` | Action endpoint, not a distinct visual page. | Preserve destination and read-state behavior. | No visual page |
| Read all `/notifications/read-all/` | Action endpoint, not a distinct visual page. | Preserve current action and feedback behavior. | No visual page |

## Manufacturer

| Page / route | Current visual concerns | Target pattern | Phase |
|---|---|---|---|
| Dashboard `/manufacturer/dashboard/` | Operational records and quote actions need the later route-level density pass. | Compact title/context, primary listing action, grouped quote/order rows. | 7A shared; 7B manufacturer |
| Create listing `/manufacturer/listings/create/` | Long form needs deliberate grouping and width discipline. | Bounded grouped form with preview/media and one primary save action. | 7A shared; 7B manufacturer |
| Edit listing `/manufacturer/listings/<id>/edit/` | Shared long form; needs parity with create form. | Same form pattern as create with explicit edit context. | 7A shared; 7B manufacturer |
| Listing management `/manufacturer/listings/` | Listing rows and availability states need efficient operations. | Compact listing table/rows, clear availability and edit actions. | 7A shared; 7B manufacturer |
| Send quotation `/manufacturer/quotes/<id>/send/` | Quote details and inputs need route-level hierarchy. | Request context followed by bounded quote form and accurate restrictions. | 7A shared; 7B manufacturer |
| Quote status `/manufacturer/quotes/<id>/status/` | Action endpoint rather than a distinct page. | Preserve status transition and confirmation behavior. | No visual page |
| Respond to quotation `/quotations/<id>/respond/` | Buyer action endpoint rather than a distinct page. | Preserve acceptance/rejection wording and route behavior. | No visual page |
| Manufacturer orders `/manufacturer/orders/` | Operational records need row-based comparison and restrained statuses. | Responsive order rows with status and next action. | 7A shared; 7B manufacturer |
| Order detail `/orders/<id>/` | Shared buyer/manufacturer template contains role-specific controls. | Reuse buyer detail structure with role-appropriate actions. | 7A shared; 7B manufacturer |
| Business profile edit `/manufacturer/profile/edit/` | Long profile form needs bounded width and consistent error treatment. | Product page header and grouped form sections. | 7A shared; 7B manufacturer |
| Create/update milestones `/milestones/<id>/{complete,fund,start,respond,release}/` | POST actions on order detail, not independent pages. | Keep milestone UI in order detail and preserve simulated-payment truth. | No visual page |
| Save/remove listing `/listings/<id>/save/`, `/saved-listings/<id>/remove/` | Action endpoints, not distinct pages. | Preserve current listing state and feedback. | No visual page |

## Shared style audit findings

- `app.css` is the primary foundation but contains accumulated repeated rules and legacy aliases. The global system now defines semantic colors, a bounded spacing scale, content widths, radii, shadows, font stack, and motion timing there.
- `visual-v2.css` previously redeclared the entire color/spacing/radius/shadow token set. Those duplicate values were removed; its compatibility names now map to the app tokens. Route-specific rules remain in place.
- `trade-ledger-public.css` owns deliberate public trade-sheet and spec-row layouts. It uses the shared semantic tokens for widths, type, borders, and controls; those route layouts are retained for the later page phase.
- The two global sheets contain historical repeated button, form, header, and card rules. Phase 7A aligned the effective final shared rules; a full stylesheet rewrite or broad deletion would be unsafe because selectors overlap route-specific templates.
- Shared navigation stays in `base.html` and routes were not changed. Mobile menu behavior remains the existing accessible disclosure behavior; the shared visual treatment is now tied to the semantic system.
- Product routes intentionally reuse the global shell, typography, controls, and compact statuses. Their internal section order, record rows, and page-specific widths are queued for 7B.
