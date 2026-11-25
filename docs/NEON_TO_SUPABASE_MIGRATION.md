# Neon PostgreSQL 18 to Supabase PostgreSQL 17 Migration Preparation

**Preparation only. No Supabase project exists yet. No migration, dump, restore,
production connection, Render setting change, or cutover has been performed.**
Neon remains the current database. Django continues to use PostgreSQL through
`DATABASE_URL`; no provider-specific runtime branch is needed.

## Scope and current architecture

The known versions are Neon PostgreSQL 18.7 and Supabase PostgreSQL 17.12.
Because this is a major-version downgrade, a PostgreSQL 18 schema dump must NOT
be restored into PostgreSQL 17. This plan creates the PG17 schema from current
Django migrations, then copies logical table data. Only the PostgreSQL hosting
provider is expected to change. Render runs Django;
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
  do not leave delivery directed to the old database during or after the final
  logical copy.
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

For read-only catalog inspection using `psql`, prefer the direct endpoint when
reachable, independently of the runtime endpoint. Do not use a PG18-generated
schema dump/restore as the PG17 migration path. Compare source and target
PostgreSQL versions first. Verify UTF-8 encoding, timezone behavior, and
collation compatibility; do not change Django timezone settings speculatively.

## Prerequisites and variables

Before rehearsal, the user/operator must create the Supabase project and obtain
its provider-generated PostgreSQL URLs, selected roles, endpoint modes, TLS
details, PostgreSQL version, encoding, timezone/collation, connection limits,
backup/PITR capabilities, and restore permissions. Also verify Render network
reachability and the plan's pooling limits. None of these target details are
known or verified yet.

For the PG18-to-PG17 data copy, use the repository utility and its pinned
`psycopg2-binary` driver; do not use full-version `pg_dump`/`pg_restore` as the
schema migration path. PostgreSQL client tools may still be useful for future
read-only inspection, but are not required by the logical-copy utility. No
system software is installed by this plan. Use placeholders only:

```powershell
$env:SOURCE_DATABASE_URL = "<source-postgresql-url>"
$env:TARGET_DATABASE_URL = "<target-postgresql-url>"
```

Do not echo these variables. Keep temporary dump files outside the repository,
with restricted access and no public sync. Delete them after verification under
the operator's secure data-handling policy. `.gitignore` also excludes custom
dump/backup and compressed SQL dump extensions as a safety net.

## Rehearsal (Stage A; no production cutover)

Do not restore a PostgreSQL 18-generated schema dump into PostgreSQL 17. The
target DDL must come from current repository migrations applied to PostgreSQL
17, followed by logical row transfer.

1. **Discover and confirm schema scope before any copy.** Do not assume the
   schema scope solely from local code. Connect read-only to the source
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
          OR LEFT(table_name, LENGTH('accounts_')) = 'accounts_'
          OR LEFT(table_name, LENGTH('marketplace_')) = 'marketplace_'
          OR LEFT(table_name, LENGTH('auth_')) = 'auth_'
          OR LEFT(table_name, LENGTH('django_')) = 'django_')
   ORDER BY table_schema, table_name;
   ```

   The prefixes correspond to project apps `accounts` and `marketplace` and
   standard Django `auth_` / `django_` tables; `django_migrations` is also
   checked explicitly. This query locates representative application tables
   and is not an exhaustive inventory. Compare the result with the expected
   Django inventory: users/auth and
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

2. Confirm the target is a newly created, disposable rehearsal database. Never
   run target reset tooling against a database that was not explicitly verified
   as the intended rehearsal target.
3. Create the PG17 schema from this repository's current migrations, using the
   target URL only in a secure local environment. For PowerShell, for example:

   ```powershell
   $env:DATABASE_URL = $env:TARGET_DATABASE_URL
   python manage.py migrate
   ```

   Do not restore source schema DDL. Use the repository-pinned Django version
   (`pip install -r requirements.txt`) before rehearsal; the prior local venv
   showed Django 6.1.1 while requirements pin 6.1.2. The version pin is not
   changed. Keep `psycopg2-binary==2.9.13` unless actual PG17 compatibility
   testing demonstrates a problem.
4. Run the logical-copy utility in default dry-run mode first:

   ```powershell
   $env:SOURCE_DATABASE_URL = "<source-postgresql-url>"
   $env:TARGET_DATABASE_URL = "<target-session-pooler-postgresql-url>"
   python scripts/logical_pg_migration.py --dry-run
   ```

   It expects PostgreSQL 18 source and PostgreSQL 17 target, inspects only the
   confirmed `public` schema, compares source/target table and column metadata,
   complete ordered foreign-key metadata (columns, actions, match and
   deferrability), primary/unique constraints, and migration app/name state,
   validates the target
   freshness allowlist, computes parent-first table order, and reports counts.
   It does not print connection URLs or row contents. The utility uses the
   ordinary PostgreSQL URI; use Supabase Session pooler for the current IPv4
   rehearsal environment, not Transaction pooler.
5. Review dry-run results. The fresh target may contain Django migration rows,
   content types and permissions, but no unknown user/business rows. Exact copy
   intentionally replaces those generated rows with source rows so IDs and
   foreign-key references are preserved. The utility refuses other target
   rows, mismatched table/column/FK structure, mismatched migration app/name
   history, unsupported versions, FK cycles, or source/target identity matches.
   It also refuses target FKs from outside the verified `public` table set that
   reference an application table.
   Same-source/target detection compares server-returned facts (`current_database`,
   server address and port) where available. A pooler or proxy may expose its
   own endpoint rather than uniquely identify the backend database, especially
   when different pooler endpoints are used. Treat identity detection as
   defense-in-depth: use separate source/target URLs, verify the disposable
   target with the operator, and require the exact `--expected-target-database`
   plus `--confirm-target-reset` execution gates. Session pooler remains the
   planned IPv4-compatible rehearsal option; its endpoint facts do not replace
   those confirmations.
6. Only after confirming the disposable target identity and dry-run results,
   execute the target-only transactional replacement with both explicit flags
   and the exact target database name:

   ```powershell
   python scripts/logical_pg_migration.py --execute --confirm-target-reset --expected-target-database "<exact-rehearsal-database-name>"
   ```

   Source is placed in a read-only transaction. The target is reset and copied
   inside a transaction, clearing rows in child-first FK order with
   individually schema-qualified `DELETE` statements and no `CASCADE`; an
   external cross-schema reference aborts before reset. An error rolls target
   table changes back. Data is
   streamed table-by-table using PostgreSQL COPY text format through a
   temporary local spool, which must be protected as sensitive data and removed
   under operator policy. Sequence restart uses transactional `ALTER SEQUENCE`
   statements built from target catalog-owned sequence names. Do not run this
   against production or an unverified target.
7. After a successful copy, verify row counts for every source table against
   target. Preserve primary keys, timestamps, JSON/Decimal values, passwords,
   transaction/payment/webhook history and relationships exactly. The utility
   reports counts only, not row contents. Also verify constraints, indexes,
   sequence next values, and representative user/profile, listing/manufacturer,
   RFQ/quotation, Order/milestone/message/payment/webhook, review, notification,
   and framework relationships. Primary/unique/FK constraints are structurally
   compared before execution. Index equivalence is a post-copy rehearsal check,
   not an automated utility guarantee. No destructive repair is automated.
8. Compare source and target `django_migrations` by app and migration name; the
   target schema was created from this repository's migrations, and the copy
   replaces target-generated migration rows with the source state. Content
   types and permissions are likewise copied exactly rather than assuming
   target-generated IDs match source.
9. Point only a dedicated local application process at the rehearsal target.
   Run `manage.py check`, `manage.py showmigrations`, and read-only dashboard,
   marketplace, existing Order, and privacy-export checks using an approved
   test account. Do not run `manage.py test` or E2E against this copied dataset:
   those suites create/destroy isolated test databases. Keep standard tests and
   `config.settings_e2e` on their existing isolated local databases.

## Final cutover (Stage B; only after rehearsal approval)

This procedure is **not being executed now**. A write freeze is required so a
new Order, RFQ, message, payment state, or webhook event cannot be committed to
the source during the final logical copy and be missing from the target.
There is no built-in maintenance mode; arrange an approved temporary
restriction of public write access and coordinate the service/webhook window
before the cutover.

1. Approve rehearsal results, target connection mode, backup/PITR and rollback
   ownership, and a service window.
2. Announce and activate the write freeze. Stop signup/marketplace workflow
   writes and payment initiation. Coordinate Razorpay Test Mode webhook
   delivery so no event is accepted only by the old database during the final
   logical copy;
   pause/queue delivery where supported and account for pending deliveries.
3. Confirm no active migration-sensitive operation is in progress. Create the
   target schema by running the reviewed repository migrations on PG17, then
   perform the final logical copy with the guarded utility. Do not use a PG18
   schema dump/restore for this downgrade.
4. Run migration-state, table/critical row counts, constraints/indexes,
   sequence, relationship, payment/webhook, encoding and read-only application
   validation. Do not expose actual user data in screenshots or logs.
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
