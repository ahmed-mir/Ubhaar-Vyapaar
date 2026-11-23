# Phase 6: CI and repository security

## GitHub Actions

`.github/workflows/ci.yml` runs on pull requests targeting `main`, pushes to
`main`, weekly on Monday, and manual dispatch. The weekly run performs only
the dependency and secret scans; it skips the full Django and browser suites.
The workflow uses Python 3.13 from `.python-version` and Node 22 for the
Playwright lockfile (the project requires Node 20 or newer and has no separate
Node version file).

Pull request jobs use `pull_request`, not `pull_request_target`. Each job has
only `contents: read`; checkout does not persist its token. No repository
secret is required. Database variables are set to an empty URL and local debug
settings; Django receives a synthetic test-only key, Cloudinary is explicitly
disabled, and Sentry is disabled. The application settings select local SQLite
for standard checks/tests; E2E tests and the Playwright-managed server use
`config.settings_e2e` and `db_e2e.sqlite3`. No job runs the Render build script
or connects to a remote database. `collectstatic` runs separately with these
local settings.

### Checks and required status names

Require these six checks before merge (the displayed check run is prefixed by
`CI and repository security /`):

- `Django validation` — system check, migration check, Django test suite,
  static collection, and changed-line whitespace check.
- `E2E settings tests` — Django tests under `config.settings_e2e`.
- `Playwright` — `npm ci`, Chromium installation, and
  `npx playwright test --workers=1` against the local E2E server.
- `Python dependency audit` — `pip-audit --requirement requirements.txt`.
- `Node dependency audit` — `npm audit --audit-level=high` against the tracked
  lockfile; high and critical advisories fail the job.
- `Secret scan` — Gitleaks scans current committed content and fetched Git
  history. Output redacts detected values.

The three security jobs also run on the weekly schedule. Playwright uses one
worker to reduce intermittent resource timeouts. Traces, screenshots, and the
HTML/JSON reports upload only when that job fails and expire after seven days.
They contain local synthetic test data. No dependency cache or database file
is cached or uploaded.

GitHub Actions are pinned to verified full commit SHAs; Dependabot proposes
weekly action updates. Pip and npm runtime dependency pins/lockfiles are not
rewritten by this phase. `pip-audit` is pinned in `requirements-security.txt`
as a CI-only tool and is not added to production requirements. Gitleaks is
downloaded at a fixed release version and checked against its pinned SHA-256
checksum before use.

## Dependency and secret findings

Do not merge through a failing vulnerability or secret scan. Upgrade to a
patched compatible version and rerun CI. If a finding is a false positive or
has no available fix, document the exact package/finding, affected version,
review date, and follow-up plan. Keep any exception scoped to the exact
fingerprint or dependency; never ignore a whole directory or disable a rule
globally. Do not put real credentials in tests or allowlists. Gitleaks reports
are redacted; do not paste secret values into issues or logs. If a real secret
is found in history, treat it as exposed and use the provider's credential
response process; this phase does not rewrite history or rotate credentials.

`.env`, `.env.*` (except `.env.example`), SQLite databases, Playwright reports,
and test results remain ignored. CI does not read a developer `.env`.

## Dependabot

`.github/dependabot.yml` checks `pip`, `npm`, and `github-actions` weekly, with
patch/minor updates grouped and major updates proposed separately. PRs are
capped at five open updates per ecosystem. Dependabot does not auto-merge.
Dependabot alerts and security updates remain GitHub account/repository
features and must be checked manually.

## Branch protection and provider-side checks

Repository files cannot enable GitHub branch protection. In repository
settings, manually require a pull request and all six status checks listed
above, block force pushes and branch deletion on `main`, and consider requiring
conversation resolution and restricting direct pushes. Confirm GitHub-native
secret scanning, push protection, and Dependabot alerts separately; this
workflow does not establish that those provider features are enabled.

Ordinary pull request validation needs no secrets, including for forked PRs.
There is no `pull_request_target`, write permission, auto-merge, or workflow
step that evaluates PR titles or branch names as shell commands. The secret
scan uses only a read-only checkout and does not post comments.

## Local commands

From the repository root, useful equivalents are:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py test
.\venv\Scripts\python.exe manage.py test --settings=config.settings_e2e
npx playwright test --workers=1
python -m pip install -r requirements-security.txt
pip-audit --requirement requirements.txt
npm audit --audit-level=high
```

The secret scan can be reproduced with Gitleaks 8.30.1 after fetching Git
history: `gitleaks git --redact=100 --log-opts="--all" .`. CI validates changed
lines with `git diff --check`. Do not point these commands at production or
provide production credentials.
