# Production Database Runbook

## Current architecture

- Django uses `dj-database-url` and reads `DATABASE_URL` when it is present.
- Without `DATABASE_URL`, local development falls back to the ignored SQLite file `db.sqlite3`.
- Production should use a managed PostgreSQL database. The repository does not provision, retain, or back up that database.
- The Render service startup script runs `python manage.py migrate` after static collection.

## Durability and backups

The code does not create backups or verify provider retention. Backup frequency, point-in-time recovery, expiration limits, and restore testing must be configured and confirmed in the PostgreSQL provider or Render dashboard. A free or trial database plan may have limited retention, suspension, expiry, storage, or recovery guarantees; do not assume it is durable without provider confirmation.

## Migration procedure

1. Confirm the target service uses the intended PostgreSQL `DATABASE_URL`.
2. Review the migration files and run `python manage.py makemigrations --check --dry-run` locally.
3. Take or confirm a provider snapshot/backup before destructive or irreversible changes.
4. Apply migrations in a controlled deploy using `python manage.py migrate`.
5. Check the deploy logs, `/health/`, admin login, and core read/write flows.

Do not use `makemigrations` as part of the production startup command. Review generated migrations before committing them.

## Restore procedure

Use the provider’s documented restore or point-in-time recovery flow to create or restore a PostgreSQL instance. After the provider reports recovery complete, set the service `DATABASE_URL` to the restored database, deploy/restart, run `python manage.py migrate`, and verify `/health/`, admin, authentication, marketplace reads, and a controlled write flow. Keep the original database untouched until the restored instance is validated.

## Before destructive migrations

- Capture a provider backup or snapshot and record its timestamp.
- Test the migration against a recent non-production copy where possible.
- Confirm rollback or forward-repair steps; Django migrations are not automatically reversible.
- Review data-loss and locking implications with the operator.
- Schedule the change for a monitored window and retain the migration logs.

## Provider configuration outside this repository

- Managed PostgreSQL plan, storage, extensions, backups, retention, and recovery testing.
- Render environment variable `DATABASE_URL` pointing to that database.
- Access controls, rotation, alerting, and provider billing/expiry settings.

## Incident notes

If the database is unavailable, preserve logs, avoid repeated destructive retries, check provider status and connection limits, and verify the active `DATABASE_URL` without printing it. If the database plan has no backups or expiry protection, treat data recovery as uncertain and escalate before making changes.
