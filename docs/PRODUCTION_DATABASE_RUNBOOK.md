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

The code does not create backups or verify provider retention. Backup frequency,
point-in-time recovery, expiration limits, and restore testing must be configured
and confirmed in the PostgreSQL provider or Render dashboard. Do not assume a
database plan is durable without provider confirmation.

## Migration procedure

1. Confirm the target service uses the intended PostgreSQL `DATABASE_URL` in
   the provider dashboard without printing the value.
2. Review migration files and run
   `python manage.py makemigrations --check --dry-run` locally.
3. Take or confirm a provider snapshot/backup before destructive or irreversible
   changes.
4. Apply reviewed migrations through the controlled deployment process.
5. Check deploy logs, `/health/`, admin login, and approved core flows.

Do not use `makemigrations` as part of production startup. Review generated
migrations before committing them.

## Restore procedure

Use the provider's documented restore or point-in-time recovery flow to create
or restore a PostgreSQL instance. After provider recovery completes, set the
service `DATABASE_URL` to the restored database, deploy/restart, run the
approved migration process, and verify `/health/`, admin, authentication, and
approved reads/writes. Keep the original database untouched until the restored
instance is validated.

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
database.
