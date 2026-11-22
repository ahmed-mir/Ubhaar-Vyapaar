# Workflow integrity hardening (internal)

## Idempotent creation actions

Buy Now and Request Quote forms receive server-signed random action tokens. Each token is bound to the authenticated user, action type, and listing. The token is validated only after the normal authentication, role, listing visibility, and current eligibility checks. A SHA-256 digest is stored on the resulting `Order` or `QuoteRequest`; the raw token is not persisted or logged.

Each resulting-object field has a database unique constraint. Replaying a valid token returns the existing order or RFQ. A fresh GET produces a fresh token, so a buyer may intentionally purchase or request a quote for the same listing again. New orders, milestones, and notifications are created in one transaction; notification side effects occur only for the request that wins the unique insert.

The action digest lives as long as its business object, so there is no separate token table or cleanup command. Existing rows use `NULL` digests and require no backfill. Keep order and request records under their normal retention rules so their replay keys remain present.

Quotation acceptance already uses a conditional `SENT`-to-response update in a transaction, with a one-to-one quotation/order relation. Only the request that changes the state creates the order and notifications.

## Milestone transitions

Milestone submission and Buyer response now use conditional updates inside transactions and lock the parent order while applying the transition and updating order status. Notifications are sent only when the conditional update changes one row. Funding, start, and release keep their existing conditional updates and role/ownership checks. Milestone percentages, labels, sequence, and payment behavior are unchanged.

## Concurrency testing limits

Local Django tests verify replay behavior, uniqueness, transition guards, and single side-effect behavior using the configured SQLite test database. SQLite does not provide PostgreSQL row-lock semantics, so the tests do not claim to simulate simultaneous PostgreSQL transactions. Production database constraints and transactions provide the cross-worker race guard; do not run concurrency tests against production.

## Preserved protections

Phase 1 database and E2E isolation settings and Phase 2 authentication abuse limits are unchanged. No production/provider access, payment changes, background worker, cache service, or scheduler is required for this phase.
