# Neon to Supabase PostgreSQL Migration Preparation

**Preparation only. No Supabase project exists yet. No migration, dump, restore,
production connection, Render setting change, or cutover has been performed.**
Neon remains the current database. Django continues to use PostgreSQL through
`DATABASE_URL`; no provider-specific runtime branch is needed.

## Scope and current architecture

Only the PostgreSQL hosting provider is expected to change. Render runs Django;
Cloudinary continues to serve current media; Razorpay remains in Test Mode;
Django authentication and authorization remain authoritative. This plan does
not use Supabase REST, Auth, or Storage, add RLS to Django tables, or add a
Supabase SDK.

Production settings require `DEBUG=False` plus a PostgreSQL `DATABASE_URL`,
reject SQLite, and enforce TLS (`sslmode=require`, preserving `verify-ca` and
`verify-full`). Missing production URLs fail closed. `manage.py test` ignores an
inherited URL; E2E clears it and uses isolated `db_e2e.sqlite3`. These Phase 1
behaviors must remain unchanged. `/ready/` continues its provider-neutral
database query.

Runtime references to database hosting are provider-agnostic. Neon references
found in the repository are documentation/E2E guidance, not runtime branches.
The build/operations documentation has no Render service manifest or Procfile;
the configured Render build/start commands must be verified in its dashboard.

## Audit findings

- Driver: `psycopg2-binary==2.9.13`; installed Django is 6.1.1 in the audit
  environment (requirements pin Django 6.1.2). No driver upgrade is proposed.
- Connection persistence: `CONN_MAX_AGE=600`; no `CONN_HEALTH_CHECKS` or driver
  pool is configured. Production `connect_timeout` defaults to 10 seconds and
  preserves a positive finite URL value. TLS normalization remains enabled.
- No application-required PostgreSQL extension was found in models or
  migrations. No custom schema, trigger, view, or sequence SQL was found.
  Django application tables use the default schema (normally `public`); confirm
  actual source schemas during the future operator-led rehearsal. Do not dump
  Supabase-managed schemas wholesale.
- No `LISTEN`/`NOTIFY`, advisory lock, temporary table, held cursor, or other
  session-level PostgreSQL feature was found. The readiness view uses
  transaction-local `SET LOCAL statement_timeout` followed by `SELECT 1`.
- One migration contains a reversible `RunPython` data operation; others are
  Django schema/data migrations. No raw provider-specific SQL was found.
- Payment webhook endpoint persists event/payment processing records. During a
  cutover, incoming webhook writes must be paused or otherwise accounted for;
  do not leave delivery directed to the old database after the final dump.
- No existing maintenance/read-only mode was found. A future cutover therefore
  requires an operator-managed write freeze (for example, temporarily
  restricting write routes/service access); no maintenance feature is added.

Application tables/models include Django auth users/groups/permissions,
`django_migrations`, sessions and admin logs; account user and auth throttle
buckets; manufacturer profiles; listings; saved listings; contact submissions
and waitlist; quote requests and quotations; Orders, milestones, messages,
notifications, reviews; payment transactions and webhook events. This is a
model-level inventory, not production row data. Confirm the deployed table list
and schema before a real dump.

## Connection mode decision after project creation

Use the provider-generated connection URL; do not construct it manually because
password characters may need URL encoding. Keep credentials only in secure
operator environment variables or Render secret configuration. Never print or
commit a URL.

1. If Render can reliably reach the Supabase direct PostgreSQL endpoint, assess
   that endpoint first.
2. If direct connectivity is unavailable or unsuitable, consider Supabase's
   shared **Session** pooler for a persistent application backend, including
   IPv4 compatibility where needed. Use the host/port shown by the future
   project dashboard; Session pooler commonly uses port 5432, but verify rather
   than assume.
3. Do not select the **Transaction** pooler by default. Its endpoint commonly
   uses port 6543, but verify. Transaction pooling may affect prepared
   statements, session state, `LISTEN`/`NOTIFY`, temporary tables, advisory
   locks, and cursor behavior. Any use requires explicit compatibility and
   concurrency review.

For `pg_dump`, `pg_restore`, and `psql`, prefer the direct endpoint when
reachable, independently of the runtime endpoint. Compare source and target
PostgreSQL versions first. Verify UTF-8 encoding, timezone behavior, and
collation compatibility; do not change Django timezone settings speculatively.

## Prerequisites and variables

Before rehearsal, the user/operator must create the Supabase project and obtain
its provider-generated PostgreSQL URLs, selected roles, endpoint modes, TLS
details, PostgreSQL version, encoding, timezone/collation, connection limits,
backup/PITR capabilities, and restore permissions. Also verify Render network
reachability and the plan's pooling limits. None of these target details are
known or verified yet.

Install/use compatible PostgreSQL client tools (`pg_dump`, `pg_restore`,
`psql`) on the operator machine; no system software is installed by this plan.
Use placeholders only:

```powershell
$env:SOURCE_DATABASE_URL = "<source-postgresql-url>"
$env:TARGET_DATABASE_URL = "<target-postgresql-url>"
```

Do not echo these variables. Keep temporary dump files outside the repository,
with restricted access and no public sync. Delete them after verification under
the operator's secure data-handling policy. `.gitignore` also excludes custom
dump/backup and compressed SQL dump extensions as a safety net.

## Rehearsal (Stage A; no production cutover)

1. **Discover and confirm schema scope before any dump.** Do not assume the
   schema scope solely from local code. Connect read-only to the deployed source
   during an approved rehearsal and inspect non-system schemas:

   ```sql
   SELECT schema_name
   FROM information_schema.schemata
   WHERE schema_name NOT IN ('information_schema', 'pg_catalog')
   ORDER BY schema_name;
   ```

   Provider/system schemas may appear in this result; their presence does not
   make them application schemas. Inspect the locations of known Django tables
   to confirm where application tables actually live:

   ```sql
   SELECT table_schema, table_name
   FROM information_schema.tables
   WHERE table_type = 'BASE TABLE'
     AND (table_name = 'django_migrations'
          OR table_name LIKE 'accounts\\_%' ESCAPE '\\'
          OR table_name LIKE 'marketplace\\_%' ESCAPE '\\')
   ORDER BY table_schema, table_name;
   ```

   Compare the result with the expected Django inventory: users/auth and
   `django_migrations`, account profiles and throttle buckets, listings,
   saved listings, RFQs, quotations, Orders, milestones, messages, payments,
   webhook events, notifications, reviews, contact/waitlist, and other Django
   framework tables. Confirm every required table is present and record the
   intentionally included application schema set. Current local audit expects
   `public`, but set `public` only if the deployed source inspection confirms
   it. Do not include Neon/provider schemas or future Supabase-managed auth,
   storage, internal, or metadata schemas without a separately reviewed reason.

   Define the confirmed schema(s) for subsequent commands. For a single
   confirmed `public` schema:

   ```powershell
   $env:APP_SCHEMA = "public"
   ```

   For multiple confirmed application schemas, use a separate explicit
   `--schema` option for each one in the dump and restore commands below. Never
   use a wildcard or include every non-system schema automatically. Preserve
   `django_migrations` by including the schema where it resides.

2. Take an approved source copy using the operator's secure procedure; never
   put dump data in Git. Use a custom-format dump scoped to the confirmed
   application schema(s), without source ownership/ACL metadata:

   ```powershell
   pg_dump --format=custom --no-owner --no-acl --schema="$env:APP_SCHEMA" --file="<restricted-path>/rehearsal.dump" "$env:SOURCE_DATABASE_URL"
   ```

   For each additional confirmed schema, add another explicit
   `--schema="<confirmed-schema>"` option. The archive itself must contain only
   intended application schemas; do not rely on restore-time exclusions to
   sanitize a broad dump. Inspect the archive before restoring:

   ```powershell
   pg_restore --list "<restricted-path>/rehearsal.dump"
   ```

   Verify the intended schema(s), `django_migrations`, and expected Django
   tables appear, and provider-managed schemas do not. This lists archive
   metadata only, not row contents. If inspection is wrong, stop and recreate a
   correctly scoped archive.

3. Restore only the scoped archive, explicitly restricting restore to the same
   confirmed schema(s) as defense in depth:

   ```powershell
   pg_restore --no-owner --no-acl --schema="$env:APP_SCHEMA" --dbname="$env:TARGET_DATABASE_URL" "<restricted-path>/rehearsal.dump"
   ```

   Repeat `--schema="<confirmed-schema>"` for each confirmed application
   schema. Verify after restore that application objects landed only in the
   intended schema(s), and that no provider-managed schema was copied. Do not
   restore Supabase Auth, Storage, internal, or provider metadata schemas, or
   Neon/provider-specific schemas, for this Django database migration. No
   extension is currently identified as required; if the source audit later
   finds one, enable/verify it through the target provider before restore rather
   than copying provider internals.

4. Connect a local or staging Django app using a secure target URL; do not
   change Render. Run `manage.py check`, migration-state inspection, and
   read-only application checks. Preserve `django_migrations`; do not rebuild
   production records from fixtures or regenerate primary keys.
5. Compare source and target count snapshots for critical application tables
   without retaining row-level data or URLs. Include users, Buyer/Manufacturer
   profiles, listings, RFQs, quotations, Orders, milestones, messages,
   payments, webhook events, and Django framework tables.
6. Verify primary/foreign keys, unique constraints, indexes, timestamps, JSON
   and Decimal values, and representative relationships: Order participants,
   quotation/order links, milestone/order links, payment/order links, and
   message/order links. Use constraint and read-only orphan checks; do not
   repair data destructively.
7. Check each serial/identity sequence is at least the maximum existing key for
   its table (and correctly handles an empty table). Use `pg_get_serial_sequence`
   / `last_value` or equivalent read-only catalog inspection; record results,
   not PII.
8. Validate UTF-8, database timezone behavior, and collation where relevant.
   Confirm Django migration state agrees with the restored schema. Test a
   dedicated account's dashboard and privacy export without exposing real
   personal data.

## Final cutover (Stage B; only after rehearsal approval)

This procedure is **not being executed now**. A write freeze is required so a
new Order, RFQ, message, payment state, or webhook event cannot be committed to
the source after the final dump and be missing from the target. There is no
built-in maintenance mode; arrange an approved temporary restriction of public
write access and coordinate the service/webhook window before the cutover.

1. Approve rehearsal results, target connection mode, backup/PITR and rollback
   ownership, and a service window.
2. Announce and activate the write freeze. Stop signup/marketplace workflow
   writes and payment initiation. Coordinate Razorpay Test Mode webhook
   delivery so no event is accepted only by the old database after the dump;
   pause/queue delivery where supported and account for pending deliveries.
3. Confirm no active migration-sensitive operation is in progress. Take the
   final Neon dump using the compatible PostgreSQL tools and secure custom
   format (`--no-owner --no-acl`, audited application schema scope).
4. Restore to Supabase. Run migration-state, table/critical row counts,
   constraints/indexes, sequence, relationship, payment/webhook, encoding and
   read-only application validation. Do not expose actual user data in
   screenshots or logs.
5. Change **only** Render's `DATABASE_URL` to the approved target runtime URL;
   leave other production settings unchanged unless rehearsal proved a need.
   Redeploy using the normal approved process.
6. Confirm `/ready/`, `/health/`, logs/error monitoring, and the read-only
   production smoke checklist. Reconcile pending webhook delivery safely.
7. Re-enable writes only after the operator approves validation. Keep Neon
   untouched during an operator-defined observation period; the duration is a
   policy/operational decision, not specified here.

## Rollback and split-brain warning

If target validation fails before writes are re-enabled, point Render's
`DATABASE_URL` back to Neon and redeploy; verify `/ready/` and read-only smoke.
Keep Neon intact. Once writes have been accepted on Supabase, Neon and Supabase
diverge: reverting the URL alone loses target-side writes. That is not a simple
rollback and requires an explicit data-reconciliation/recovery decision. Never
delete the source immediately after cutover.

## Cleanup and decommission

After successful observation and an explicit owner decision, document which
source snapshots/dumps are retained or securely removed under the approved
policy; no retention duration is invented here. Confirm Render points only to
the approved target, credentials are rotated/revoked as appropriate, and
temporary local dumps are securely handled. Decommission Neon only after the
owner approves and confirms backup/recovery requirements are met.

## Current state

Preparation only: no Supabase account/project, credentials, connection, dump,
restore, Render change, production access, or cutover exists. Neon remains the
active provider. No migration is claimed complete.
