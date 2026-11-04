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
- [x] Inventory the 35 explicit SQLite indexes plus one PostgreSQL-only Click idempotency index.
- [x] Confirm `.env.local`, `.env` and SQLite files must stay out of Git.

## 1. SQLite / PostgreSQL compatibility audit
- [x] Identify SQLite-specific connection pragmas and `sqlite3.IntegrityError` handlers.
- [x] Identify `PRAGMA table_info`, `sqlite_master`, qmark parameters, `INSERT OR IGNORE`, `IS ?`, and `lastrowid`.
- [x] Identify SQLite `GROUP_CONCAT` and case-insensitive `LIKE` behavior.
- [x] Record financial columns that should use PostgreSQL `NUMERIC(18,2)`.
- [x] Include `disputes`, `recently_viewed`, and `saved_searches`, which were present in the SQLite database but absent from the uploaded source snapshot.

## 2. PostgreSQL driver and configuration
- [x] Add psycopg 3 to backend requirements.
- [x] Load root `.env.local` as the authoritative local branch config; test mode explicitly protects `TEST_DATABASE_URL` from override.
- [x] Require `DATABASE_URL`; do not silently fall back to SQLite.
- [x] Verify the real PostgreSQL endpoint hostname against `NEON_DEVELOPMENT_DATABASE_HOST` in the importer and development Flask startup.
- [x] Add a JSON boundary conversion for PostgreSQL Decimal values.

## 3. PostgreSQL schema and versioned migrations
- [~] Add a `schema_migrations` ledger with version 1 bootstrap, version 2 legacy-column compatibility, and version 3 exact job-price type migration, and version 4 Click transaction idempotency.
- [~] Add all 22 application tables, all 35 source indexes, and one additional unique Click transaction index to the PostgreSQL bootstrap.
- [~] Map money columns, including `jobs.price`, to `NUMERIC(18,2)`.
- [~] Clone the exact local SQLite table DDL (including the three auxiliary tables) in the guarded data migration utility.
- [ ] Run and validate these schema migrations against the development branch.

## 4. Database connection and SQL compatibility layer
- [~] Add `backend/pg_compat.py` using psycopg and tuple rows.
- [~] Translate qmark placeholders safely outside quoted strings and comments.
- [~] Translate `lastrowid` through PostgreSQL `RETURNING id`.
- [~] Translate `PRAGMA table_info`, `sqlite_master`, `INSERT OR IGNORE`, `IS ?`, `GROUP_CONCAT`, and `LIKE`.
- [~] Bind monetary float parameters as `Decimal` / PostgreSQL `numeric` values.
- [~] Commit completed read transactions when query results are closed and reset cursor state between statements.
- [ ] Run a live PostgreSQL smoke test and verify all translated SQL against Neon development.

## 5. Main application SQL conversion
- [~] Route the main DB class through PostgreSQL connections.
- [~] Preserve existing API query call sites with the compatibility layer.
- [~] Remove silent schema migration exception swallowing and move legacy columns into explicit schema versions.
- [~] Add a guard against accidental empty-database bootstrap before the SQLite import.
- [ ] Complete static review of all complex filters, aggregates, and transaction boundaries.
- [~] Add PostgreSQL CI workflow and expand regression tests (including SQL translation and Click callback idempotency); the workflow run result has not yet been confirmed.

## 6. Payments, wallet, and escrow
- [~] Remove runtime CREATE/ALTER TABLE statements from `payments.py`.
- [~] Keep wallet, payment, platform, and settings schema under the central migration.
- [~] Add row-count guards to Click callback escrow and job-state updates.
- [~] Add row-count guards to wallet credits and escrow/platform ledger updates during release/refund.
- [~] Add a partial unique index for Click provider transaction IDs and return a duplicate-transaction response on concurrent conflicts.
- [~] Add a PostgreSQL regression test proving Click provider transaction IDs cannot be reused.
- [~] Add concurrent withdrawal, release, refund, and dummy-hold regression tests; execution is pending.
- [ ] Verify all financial balances and escrow totals against source data.

## 7. SQLite-to-PostgreSQL data migration utility
- [x] Add `backend/migrate_sqlite_to_postgres.py`.
- [~] Add an importer-specific integration test using a temporary SQLite fixture and a disposable PostgreSQL schema in CI; execution is pending.
- [~] Require `NEON_BRANCH=finjob-development` and explicit `--confirm-branch finjob-development`; the actual migration has not been run.
- [~] Refuse production and refuse a non-empty target schema.
- [~] Create a timestamped SQLite backup before migration.
- [~] Copy source tables, data, explicit indexes, exact Decimal financial values, and reset identity sequences.
- [ ] Run against the actual local `backend/app.db` and compare all 22 row counts and 35 indexes.
- [ ] Verify financial sums, balances, escrow, and critical user/job/payment records.

## 8. Test suite and PostgreSQL regression tests
- [~] Require a separate `TEST_DATABASE_URL` and normalize Neon pooler/direct host names in the safety check.
- [~] Refuse to run tests against the same PostgreSQL database as `DATABASE_URL`.
- [~] Truncate and reset only the dedicated test database before tests.
- [~] Add a regression test for Click provider transaction ID uniqueness.
- [~] Add PostgreSQL transaction rollback and identity-sequence regression tests; execution is pending.
- [~] Add compatibility, importer, Click callback, identity, rollback, concurrency, and application regression coverage; execution is pending.
- [~] Add parallel wallet-withdrawal, release, refund, and dummy-hold regression tests; execution is pending.

## 9. Development deployment and end-to-end verification
- [ ] Install dependencies in the local virtual environment.
- [ ] Configure a separate PostgreSQL test database.
- [~] Add a GitHub Actions workflow for syntax checks and PostgreSQL 16 integration tests; no completed run has been observed.
- [ ] Run the SQLite data migration against `finjob-development`.
- [ ] Start Flask against Neon development.
- [ ] Verify registration, login, jobs, proposals, chat, moderation, legal/community rules, Click callback, wallet, escrow, release, refund, and receipts.
- [ ] Confirm no unexpected row loss, duplicate rows, or balance drift.

## 10. Production cutover (approval required)
- [ ] Prepare backup, downtime, DNS/environment, and rollback steps.
- [ ] Review the migration result and production readiness with the project owner.
- [ ] Do not run production migrations, deploy, or cut over without explicit approval.

## 11. Work completed during this implementation pass
- [x] Fix missing `re` import in the SQLite-to-PostgreSQL importer (the schema-name validation used `re.fullmatch`).
- [x] Compare financial totals with `Decimal` arithmetic and a one-tiyin tolerance instead of converting totals back to binary floating point.
- [x] Make `PRAGMA table_info` primary-key metadata joins include the table name as well as the constraint name.
- [x] Add a real endpoint-host allow-list so a typed `NEON_BRANCH=finjob-development` label alone cannot authorize a different database host.
- [x] Import only from the verified timestamped SQLite backup snapshot, and add a regression test that mutates the live fixture after backup creation to prove the imported data remains snapshot-consistent.
- [x] Restrict Click prepare/confirm callbacks to the original provider transaction ID; mismatched IDs are rejected and repeated matching confirmations are idempotent.
- [x] Add regression tests for SQL translation and Click callback idempotency.
- [x] Add a concurrent wallet-withdrawal test that verifies two simultaneous withdrawals cannot overdraw the account.
- [x] Add concurrent release/refund regression tests that verify escrow and wallet ledgers are updated only once.
- [x] Serialize dummy escrow payment attempts with a job-row lock and test that parallel requests create only one debit, escrow hold, and ledger row.
- [x] Keep one canonical PostgreSQL 16 GitHub Actions workflow; it runs the dedicated SQL compatibility tests, importer fixture plus post-import schema migrations, and application regression suite.
- [ ] Observe a successful CI run and fix any resulting failures before calling the implementation verified.
