# Production Database Runbook

## Database selection

The relevant environment variable names are `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`,
and `DATABASE_URL`. Do not put credentials in this document or commit them.

- **Local development:** `DJANGO_DEBUG=True` with no `DATABASE_URL` uses the
  ignored `db.sqlite3` file. An explicit database URL may be used for local
  development when needed.
- **Django tests:** `manage.py test` selects local SQLite before Django creates
  its isolated test database. A shell-provided `DATABASE_URL` is ignored.
- **Playwright E2E:** `config.settings_e2e` always uses the separate,
  ignored `db_e2e.sqlite3` file. It clears `DATABASE_URL`, including a value
  inherited from the shell or loaded from `.env`.
- **Production:** `DEBUG=False` requires `DATABASE_URL`. The URL must parse as
  PostgreSQL and include a host and database name. Production connections use
  TLS (`sslmode=require`); the stricter `verify-ca` and `verify-full` modes are
  preserved. SQLite is rejected in production.

The Render startup/build architecture remains unchanged: the build script
collects static files and runs `python manage.py migrate` against the configured
production PostgreSQL URL. Do not run a production command without first
confirming its settings and target through the provider dashboard. This task
does not access or validate the production database.

## Durability and backups

The repository contains no evidence that automated backups or point-in-time
recovery are enabled. Their availability, retention window, recovery point
granularity, and restore permissions depend on the current Neon plan and must be
verified in the provider dashboard. Do not infer a retention period or claim
PITR is enabled from application configuration.

Record launch recovery objectives with the service owner before launch:

- **RPO (acceptable data loss): TBD** — the maximum data loss the service
  owner accepts after an incident.
- **RTO (acceptable recovery time): TBD** — the maximum time the service owner
  accepts before service is restored.

The provider's documented backup/PITR capability is an application continuity
requirement; actual backups, retention, access controls, and permissions are
provider-verification requirements.

## Migration procedure

1. Confirm the target service uses the intended PostgreSQL `DATABASE_URL` in
   the provider dashboard without printing the value.
2. Review migration files and run
   `python manage.py makemigrations --check --dry-run` locally.
3. Take or confirm a provider snapshot/backup before destructive or irreversible
   changes.
4. Apply reviewed migrations through the controlled deployment process.
5. Check deploy logs, `/health/`, `/ready/`, the Admin login page (GET only),
   and approved read-only core flows.

Do not use `makemigrations` as part of production startup. Review generated
migrations before committing them.

## Restore procedure

Never use production as the first restore test. A future restore drill should:

1. Record the approved recovery point, restore operator, and change approval.
2. Use the provider's documented backup/PITR flow to restore into a separate
   non-production project, branch, or database.
3. Use non-production credentials and confirm the target before running any
   command. Do not connect this drill to production.
4. Run Django `check` and inspect migration state; apply reviewed migrations
   only if the drill requires them.
5. Perform read-only verification: representative counts for Users, Orders,
   Quotations, and Milestones; confirm recent Orders exist without displaying
   personal details; request `/health/` and `/ready/`; inspect application
   pages in the isolated environment.
6. Record the recovered point, elapsed time, validation result, and approval.
   Remove the temporary restore after the drill according to provider policy.

Keep the original production database untouched until an approved recovery plan
has been validated. A real incident cutover requires an explicit owner decision,
not an automatic URL swap.

## Before destructive migrations

- Capture a provider backup or snapshot and record its timestamp.
- Test the migration against a recent non-production copy where possible.
- Confirm rollback or forward-repair steps; Django migrations are not
  automatically reversible.
- Review data-loss and locking implications with the operator.
- Schedule the change for a monitored window and retain migration logs.

## Provider configuration outside this repository

Confirm the managed PostgreSQL plan, TLS, access controls, backups, retention,
recovery testing, alerting, billing, and expiry settings in the provider
dashboards. Render's `DATABASE_URL` must point to the intended PostgreSQL
database. Verify who can create/restore branches and how restore credentials
are managed and rotated. Do not put provider values in this runbook.
