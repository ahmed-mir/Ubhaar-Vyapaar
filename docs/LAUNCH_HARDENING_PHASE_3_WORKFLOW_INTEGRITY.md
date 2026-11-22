# Workflow integrity hardening (internal)

## Idempotent creation actions

Buy Now and Request Quote forms receive server-signed random action tokens with a 24-hour maximum age. Each token is bound to the authenticated user, action type, and listing. The token is validated only after the normal authentication, role, listing visibility, and current eligibility checks. An expired token cannot create an order or request; the user must reload the form for a fresh token. A SHA-256 digest is stored on the resulting `Order` or `QuoteRequest`; the raw token is not persisted or logged.

Each resulting-object field has a database unique constraint. Replaying a valid token returns the existing order or RFQ. A fresh GET produces a fresh token, so a buyer may intentionally purchase or request a quote for the same listing again. New orders, milestones, and notifications are created in one transaction; notification side effects occur only for the request that wins the unique insert.

The action digest lives as long as its business object, so there is no separate token table or cleanup command. Existing rows use `NULL` digests and require no backfill. Keep order and request records under their normal retention rules so their replay keys remain present.

Quotation acceptance already uses a conditional `SENT`-to-response update in a transaction, with a one-to-one quotation/order relation. Only the request that changes the state creates the order and notifications.

## Milestone transitions

Every milestone state transition that recalculates `Order.status` uses one lock order inside a transaction: parent `Order` first, then `Milestone`. This includes demo funding, starting, submission, Buyer response, release, and verified payment capture. Conditional updates remain in place; notifications are sent only when a transition changes one row. `refresh_order_status` reads milestone state directly from the database rather than a potentially prefetched relation cache, and runs before the parent lock is released. Payment verification, amounts, Test Mode, and payment semantics are unchanged.

## Concurrency testing limits

Local Django tests verify replay behavior, uniqueness, transition guards, fresh aggregate status, and single side-effect behavior using the configured SQLite test database. SQLite does not provide PostgreSQL row-lock semantics, so the tests do not claim to simulate simultaneous PostgreSQL transactions. The code uses parent-first row locks and conditional updates for PostgreSQL; true PostgreSQL concurrent transactions were not executed against production. Do not run concurrency tests against production.

## Preserved protections

Phase 1 database and E2E isolation settings and Phase 2 authentication abuse limits are unchanged. No production/provider access, payment changes, background worker, cache service, or scheduler is required for this phase.
