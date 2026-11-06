# FinJob PostgreSQL migration — runbook

This runbook applies only to the `feature/postgresql-migration` work branch and Neon `finjob-development` branch. Do not use a production connection string.

## 1. Install the backend dependencies

Run these commands from the repository root in the activated Python virtual environment:

```cmd
python -m pip install -r backend/requirements.txt
```

## 2. Check the Neon development configuration

The repository root `.env.local` should contain the connection string pulled from the Neon development branch, plus:

```env
NEON_BRANCH=finjob-development
DATABASE_SCHEMA=finjob_data
NEON_DEVELOPMENT_DATABASE_HOST=ep-your-dev-endpoint.region.aws.neon.tech
```

The importer also compares the real hostname in `DATABASE_URL` with `NEON_DEVELOPMENT_DATABASE_HOST`. Copy only the exact host portion from the development branch connection string (include `-pooler` when present). This separate allow-list prevents a production DSN from passing merely because `NEON_BRANCH` was typed as `finjob-development`. Do not copy the username, password, query parameters, or full DSN into this setting.

FinJob uses the isolated `finjob_data` schema by default in development. This is intentional: Neon branches can contain a copy of tables in `public`; the migration must not overwrite those. The importer creates/uses only `finjob_data`, leaving existing `public` tables unchanged. The Flask app uses the same schema automatically.

Do not paste the full connection string into chat, tickets, source code, or GitHub. Do not commit `.env.local`.

The backend test suite needs a **separate PostgreSQL database** in `TEST_DATABASE_URL`. It must not point to the same database as `DATABASE_URL`. The test suite truncates tables in its test database before running.

Keep this setting off for the application database:

```env
FINJOB_ALLOW_EMPTY_DB_BOOTSTRAP=0
```

## 3. Migrate the existing SQLite data first

**Do not start the Flask app against an empty Neon database before this step.** The app intentionally refuses to initialize an empty database unless explicitly allowed, to avoid accidentally creating a fresh schema and blocking the import of existing SQLite data.

From the repository root, run:

```cmd
python backend/migrate_sqlite_to_postgres.py --confirm-branch finjob-development
```

The script:
- creates/uses only the configured target schema (default `finjob_data`), not the branch's existing `public` schema;
- reads `backend/app.db` in read-only mode;
- validates the SQLite integrity check;
- creates a consistent timestamped SQLite backup using SQLite's backup API;
- refuses production and refuses a non-empty target schema;
- imports the source table definitions, data, explicit indexes, and identity sequence positions;
- compares table columns, row counts, index names, and key financial totals;
- rolls back all target changes if any step fails.

The script prints a summary. Do not proceed unless it ends with `Migratsiya muvaffaqiyatli yakunlandi.`

If the script refuses the target because it is not empty, stop and inspect the branch/database. Do not drop tables or delete data to force the migration.

## 4. Run the PostgreSQL tests against the separate test database

Make sure `TEST_DATABASE_URL` refers to a dedicated disposable test database. In Windows CMD, set the empty-schema bootstrap flag only in the terminal used for tests:

```cmd
set FINJOB_ALLOW_EMPTY_DB_BOOTSTRAP=1
cd backend
python -m unittest -v test_pg_compat
python -m unittest -v test_suite
```

The test suite refuses `FINJOB_ENV=production`, requires `TEST_DATABASE_URL`, checks it is distinct from `DATABASE_URL`, and truncates only the test database schema.

After testing, close that terminal or reset the flag:

```cmd
set FINJOB_ALLOW_EMPTY_DB_BOOTSTRAP=0
```

## 5. Verify development end to end

Only after the data migration and both test commands succeed:
- start the Flask backend using the development `DATABASE_URL`;
- verify registration, login, user profiles, services, jobs, proposals, messaging, moderation, appeals/disputes, notifications, and favorites;
- verify Click prepare/complete callbacks, wallet top-ups/withdrawals, escrow holds, release, refund, and receipts;
- compare balances and escrow totals with the SQLite backup.

Do not run the one-time SQLite importer a second time. It deliberately refuses a non-empty target.

## 6. Production

This migration code does not run production cutover. Production requires a separate backup, final data sync, maintenance window, explicit project-owner approval, and rollback plan. Do not change production environment variables or run production migrations as part of this development test.
