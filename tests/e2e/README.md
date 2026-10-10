# Production E2E smoke tests

These Playwright tests target the deployed Ubhaar-Vyapaar app through
`UBHAAR_BASE_URL`. They create timestamped disposable users/listings and do not
delete production data.

## Required environment

```powershell
$env:UBHAAR_BASE_URL = "https://ubhaar-vyapaar.onrender.com"
$env:TEST_USER_PASSWORD = "<strong disposable password>"
```

## Optional environment

Set these only when the suite is allowed to verify a disposable manufacturer
through Django admin. Without them, KYC-dependent marketplace/order tests are
skipped.

```powershell
$env:TEST_ADMIN_USERNAME = "<admin username>"
$env:TEST_ADMIN_PASSWORD = "<admin password>"
```

Password reset delivery is not verified through an inbox. The test only checks
that the reset request page accepts a submission and shows the done page.

## Run

```powershell
npm install
npx playwright install chromium
npm run test:e2e
npm run test:e2e:report
```

Failure screenshots, traces, videos, and JSON results are written under
`test-results/`. The readable HTML report is written to `playwright-report/`.
