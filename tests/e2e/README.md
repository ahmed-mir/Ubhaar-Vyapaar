# Playwright E2E tests

## Local E2E

The default Playwright configuration starts Django with
`config.settings_e2e`. That settings module always uses the isolated local
`db_e2e.sqlite3` database and ignores `DATABASE_URL`, even if one is present in
the parent shell or `.env`. The local suite must never be pointed at production
or Neon. Playwright applies migrations to this E2E-only file before starting
the local server and seeds fictional demo records there; it does not migrate or
seed `db.sqlite3`.

```powershell
npm install
npx playwright install chromium
npx playwright test
```

The test runner writes reports and artifacts under `test-results/` and
`playwright-report/`.

## Remote E2E mode

Setting `UBHAAR_BASE_URL` switches Playwright away from its local E2E server.
Some remote E2E tests create users, listings, or other persistent records.
Use that mode only against an isolated staging environment with disposable test
data and explicitly authorized test accounts. Never point the data-creating
suite at production; it does not clean up production data.

Production checks must follow the read-only procedure in
[`docs/PRODUCTION_SMOKE_TEST.md`](../../docs/PRODUCTION_SMOKE_TEST.md). Do not
provide production credentials to the test runner.
