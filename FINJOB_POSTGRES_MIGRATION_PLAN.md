# FinJob: SQLite → PostgreSQL / Neon migration plan

**Target for all development work:** Neon branch `finjob-development`  
**Production:** read-only / no migration or cutover without explicit approval.  
**Source of truth for data migration:** the local `backend/app.db` file and its schema. Never commit that database or credentials.

Status meanings:
- [x] Completed based on source/inventory review.
- [~] Implemented in code but still requires runtime verification.
- [ ] Not completed.

## 0. Repository and environment inventory
- [x] Confirm the working branch is `feature/postgresql-migration`.
- [x] Confirm local SQLite main database and backup integrity checks were reported as `ok`.
- [x] Inventory the 22 application tables and row counts.
- [x] Inventory the 35 explicit SQLite indexes.
- [x] Confirm `.env.local`, `.env` and SQLite files must stay out of Git.

## 1. SQLite / PostgreSQL compatibility audit
- [x] Identify SQLite-specific connection pragmas and `sqlite3.IntegrityError` handlers.
- [x] Identify `PRAGMA table_info`, `sqlite_master`, qmark parameters, `INSERT OR IGNORE`, `IS ?`, and `lastrowid`.
- [x] Identify SQLite `GROUP_CONCAT` and case-insensitive `LIKE` behavior.
- [x] Record financial columns that should use PostgreSQL `NUMERIC(18,2)`.
- [x] Include `disputes`, `recently_viewed`, and `saved_searches`, which were present in the SQLite database but absent from the uploaded source snapshot.

## 2. PostgreSQL driver and configuration
- [x] Add psycopg 3 to backend requirements.
- [x] Load root `.env.local` and backend `.env` without overriding process environment variables.
- [x] Require `DATABASE_URL`; do not silently fall back to SQLite.
- [x] Add a JSON boundary conversion for PostgreSQL Decimal values.

## 3. PostgreSQL schema and versioned migrations
- [~] Add a `schema_migrations` ledger and a version-1 schema bootstrap.
- [~] Add the 22-table schema and all 35 named indexes to the PostgreSQL bootstrap.
- [~] Map money-related REAL columns to `NUMERIC(18,2)` at the SQL compatibility boundary.
- [ ] Review the exact local SQLite DDL for the three tables missing from the uploaded source snapshot.
- [ ] Add future schema changes as explicit version 2+ migrations; never add runtime DDL to payment routes.

## 4. Database connection and SQL compatibility layer
- [~] Add `backend/pg_compat.py` using psycopg and tuple rows.
- [~] Translate qmark placeholders safely outside quoted strings and comments.
- [~] Translate `lastrowid` through PostgreSQL `RETURNING id`.
- [~] Translate `PRAGMA table_info`, `sqlite_master`, `INSERT OR IGNORE`, `IS ?`, `GROUP_CONCAT`, and `LIKE`.
- [~] Commit completed read transactions when query results are closed.
- [ ] Run a live PostgreSQL smoke test and verify all translated SQL against Neon development.

## 5. Main application SQL conversion
- [~] Route the main DB class through PostgreSQL connections.
- [~] Preserve existing API query call sites with the compatibility layer.
- [~] Remove silent schema migration exception swallowing.
- [ ] Complete static review of all complex filters, aggregates, and transaction boundaries.
- [ ] Run the full application test suite against the dedicated PostgreSQL test database.

## 6. Payments, wallet, and escrow
- [~] Remove runtime CREATE/ALTER TABLE statements from `payments.py`.
- [~] Keep wallet, payment, platform, and settings schema under the central migration.
- [~] Add row-count guards to Click callback escrow and job-state updates.
- [~] Add row-count guards to wallet credits during release/refund.
- [ ] Add concurrent/idempotency regression tests for Click callback, release, refund, dummy hold, and withdrawal.
- [ ] Verify all financial balances and escrow totals against source data.

## 7. SQLite-to-PostgreSQL data migration utility
- [~] Add `backend/migrate_sqlite_to_postgres.py`.
- [~] Require `NEON_BRANCH=finjob-development` and explicit `--confirm-branch finjob-development`.
- [~] Refuse production and refuse a non-empty target database.
- [~] Create a timestamped SQLite backup before migration.
- [~] Copy source tables, data, explicit indexes, and reset identity sequences.
- [ ] Run against the actual local `backend/app.db` and compare all 22 row counts and 35 indexes.
- [ ] Verify financial sums, balances, escrow, and critical user/job/payment records.

## 8. Test suite and PostgreSQL regression tests
- [~] Require a separate `TEST_DATABASE_URL`.
- [~] Refuse to run tests against the same DSN as `DATABASE_URL`.
- [~] Truncate and reset only the dedicated test database before tests.
- [ ] Add transaction rollback, unique-constraint, sequence, and concurrent payment regression tests.
- [ ] Execute the complete suite and fix every failure.

## 9. Development deployment and end-to-end verification
- [ ] Install dependencies in the local virtual environment.
- [ ] Configure a separate PostgreSQL test database.
- [ ] Run syntax/import checks and all tests.
- [ ] Run the SQLite data migration against `finjob-development`.
- [ ] Start Flask against Neon development.
- [ ] Verify registration, login, jobs, proposals, chat, moderation, legal/community rules, Click callback, wallet, escrow, release, refund, and receipts.
- [ ] Confirm no unexpected row loss, duplicate rows, or balance drift.

## 10. Production cutover (approval required)
- [ ] Prepare backup, downtime, DNS/environment, and rollback steps.
- [ ] Review the migration result and production readiness with the project owner.
- [ ] Do not run production migrations, deploy, or cut over without explicit approval.
