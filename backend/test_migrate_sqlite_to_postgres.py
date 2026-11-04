import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import psycopg

import migrate_sqlite_to_postgres as migration_module
from migrate_sqlite_to_postgres import migrate, ensure_development_target


class SQLiteToPostgreSQLMigrationTests(unittest.TestCase):
    DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
    TARGET_SCHEMA = "finjob_import_test"

    @classmethod
    def setUpClass(cls):
        if not cls.DATABASE_URL.startswith(("postgres://", "postgresql://")):
            raise RuntimeError("DATABASE_URL PostgreSQL CI test database DSN talab qilinadi.")
        cls.connection = psycopg.connect(cls.DATABASE_URL)
        cls.connection.execute(
            f'CREATE SCHEMA IF NOT EXISTS "{cls.TARGET_SCHEMA}"'
        )
        cls.connection.execute(
            f'DROP SCHEMA "{cls.TARGET_SCHEMA}" CASCADE'
        )
        cls.connection.commit()
        cls.connection.close()

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(cls.DATABASE_URL) as connection:
            connection.execute(
                f'DROP SCHEMA IF EXISTS "{cls.TARGET_SCHEMA}" CASCADE'
            )

    def test_development_guard_checks_the_real_dsn_host(self):
        with patch.dict(
            os.environ,
            {
                "FINJOB_ENV": "development",
                "NEON_BRANCH": "finjob-development",
                "DATABASE_URL": "postgresql://postgres:postgres@127.0.0.1:5432/finjob_migration_test",
                "NEON_DEVELOPMENT_DATABASE_HOST": "production-endpoint.example.neon.tech",
            },
        ):
            with self.assertRaises(RuntimeError):
                ensure_development_target("finjob-development")

    def test_development_guard_accepts_only_the_expected_endpoint_host(self):
        with patch.dict(
            os.environ,
            {
                "FINJOB_ENV": "development",
                "NEON_BRANCH": "finjob-development",
                "DATABASE_URL": "postgresql://postgres:postgres@127.0.0.1:5432/finjob_migration_test",
                "NEON_DEVELOPMENT_DATABASE_HOST": "127.0.0.1",
            },
        ):
            self.assertTrue(
                ensure_development_target("finjob-development").startswith("postgresql://")
            )

    def test_migrate_tables_rows_money_indexes_and_identity(self):
        with tempfile.TemporaryDirectory(prefix="finjob-migration-test-") as temp_dir:
            sqlite_path = Path(temp_dir) / "sample.sqlite3"
            source = sqlite3.connect(sqlite_path)
            try:
                source.executescript(
                    """
                    CREATE TABLE users(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        balance REAL NOT NULL DEFAULT 0
                    );
                    CREATE TABLE jobs(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        price INTEGER,
                        agreed_price REAL
                    );
                    CREATE TABLE payments(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        payment_uuid TEXT UNIQUE NOT NULL,
                        job_id INTEGER UNIQUE,
                        payer_id INTEGER NOT NULL,
                        payee_id INTEGER NOT NULL,
                        amount REAL,
                        provider TEXT NOT NULL DEFAULT 'click',
                        status TEXT NOT NULL DEFAULT 'pending',
                        provider_transaction_id TEXT DEFAULT '',
                        created_at TEXT
                    );
                    CREATE TABLE services(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        parent_id INTEGER,
                        created_by INTEGER
                    );
                    CREATE TABLE ratings(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id INTEGER,
                        from_user INTEGER,
                        to_user INTEGER,
                        score INTEGER,
                        comment TEXT
                    );
                    CREATE TABLE messages(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sender_id INTEGER,
                        receiver_id INTEGER,
                        job_id INTEGER,
                        message TEXT,
                        sent_at TEXT
                    );
                    CREATE TABLE reports(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        reporter_id INTEGER NOT NULL,
                        reported_user_id INTEGER,
                        job_id INTEGER,
                        reason TEXT NOT NULL,
                        details TEXT DEFAULT '',
                        status TEXT DEFAULT 'open',
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE portfolio_items(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        url TEXT DEFAULT '',
                        image_url TEXT DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE platform_wallet(
                        id INTEGER PRIMARY KEY CHECK(id=1),
                        balance REAL NOT NULL DEFAULT 0,
                        escrow_balance REAL NOT NULL DEFAULT 0
                    );
                    CREATE TABLE typing_states(
                        job_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY(job_id,user_id)
                    );
                    CREATE INDEX idx_users_balance ON users(balance);
                    """
                )
                source.execute(
                    "INSERT INTO users(id,username,balance) VALUES(17,?,?)",
                    ("migration-user", 12345.67),
                )
                source.execute(
                    "INSERT INTO jobs(id,price,agreed_price) VALUES(26,?,?)",
                    (199500, 199500.25),
                )
                source.execute(
                    "INSERT INTO payments(id,job_id,amount,created_at) VALUES(39,26,?,?)",
                    (199500.25, "2026-11-04T00:00:00+00:00"),
                )
                source.execute(
                    "INSERT INTO platform_wallet(id,balance,escrow_balance) VALUES(1,?,?)",
                    (50.25, 199500.25),
                )
                source.execute(
                    "INSERT INTO typing_states(job_id,user_id,updated_at) VALUES(26,17,123.456)"
                )
                source.commit()
            finally:
                source.close()

            with patch.dict(
                os.environ,
                {
                    "FINJOB_ENV": "development",
                    "NEON_BRANCH": "finjob-development",
                    "DATABASE_URL": self.DATABASE_URL,
                    "DATABASE_SCHEMA": self.TARGET_SCHEMA,
                    "NEON_DEVELOPMENT_DATABASE_HOST": "127.0.0.1",
                },
            ):
                original_create_backup = migration_module.create_backup
                created_backups = []

                def create_backup_then_mutate_live_source(source_connection, source_path):
                    backup_path = original_create_backup(source_connection, source_path)
                    created_backups.append(backup_path)
                    with sqlite3.connect(source_path) as live_source:
                        live_source.execute(
                            "UPDATE users SET balance=? WHERE id=17",
                            (99999.99,),
                        )
                    return backup_path

                with patch(
                    "migrate_sqlite_to_postgres.create_backup",
                    side_effect=create_backup_then_mutate_live_source,
                ):
                    migrate(sqlite_path, "finjob-development")

                self.assertEqual(len(created_backups), 1)
                with sqlite3.connect(created_backups[0]) as backup_check:
                    self.assertEqual(
                        backup_check.execute(
                            "SELECT balance FROM users WHERE id=17"
                        ).fetchone()[0],
                        12345.67,
                    )
                with sqlite3.connect(sqlite_path) as live_check:
                    self.assertEqual(
                        live_check.execute(
                            "SELECT balance FROM users WHERE id=17"
                        ).fetchone()[0],
                        99999.99,
                    )

            with psycopg.connect(self.DATABASE_URL) as target:
                target.execute(f'SET search_path TO "{self.TARGET_SCHEMA}"')
                self.assertEqual(
                    target.execute("SELECT username,balance FROM users WHERE id=17").fetchone(),
                    ("migration-user", Decimal("12345.67")),
                )
                self.assertEqual(
                    target.execute("SELECT price,agreed_price FROM jobs WHERE id=26").fetchone(),
                    (Decimal("199500.00"), Decimal("199500.25")),
                )
                self.assertEqual(
                    target.execute("SELECT amount FROM payments WHERE id=39").fetchone()[0],
                    Decimal("199500.25"),
                )
                self.assertEqual(
                    target.execute(
                        "SELECT balance,escrow_balance FROM platform_wallet WHERE id=1"
                    ).fetchone(),
                    (Decimal("50.25"), Decimal("199500.25")),
                )
                self.assertEqual(
                    target.execute(
                        "SELECT updated_at FROM typing_states WHERE job_id=26 AND user_id=17"
                    ).fetchone()[0],
                    123.456,
                )
                self.assertEqual(
                    target.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall(),
                    [(1,)],
                )
                self.assertTrue(
                    target.execute(
                        """
                        SELECT 1 FROM pg_indexes
                        WHERE schemaname=%s AND indexname='idx_users_balance'
                        """,
                        (self.TARGET_SCHEMA,),
                    ).fetchone()
                )

                inserted_id = target.execute(
                    "INSERT INTO users(username,balance) VALUES(%s,%s) RETURNING id",
                    ("post-migration-user", Decimal("1.00")),
                ).fetchone()[0]
                self.assertGreater(inserted_id, 17)

            # The real application startup must apply the imported schema's
            # v2/v3/v4 migrations without replacing any imported rows.
            with patch.dict(
                os.environ,
                {
                    "FINJOB_ENV": "development",
                    "FINJOB_TEST_MODE": "1",
                    "FINJOB_ALLOW_EMPTY_DB_BOOTSTRAP": "0",
                    "NEON_BRANCH": "finjob-development",
                    "NEON_DEVELOPMENT_DATABASE_HOST": "127.0.0.1",
                    "DATABASE_URL": self.DATABASE_URL,
                    "DATABASE_SCHEMA": self.TARGET_SCHEMA,
                    "SECRET_KEY": "migration-test-secret",
                },
            ):
                sys.modules.pop("main", None)
                importlib.import_module("main")

            with psycopg.connect(self.DATABASE_URL) as migrated:
                migrated.execute(f'SET search_path TO "{self.TARGET_SCHEMA}"')
                self.assertEqual(
                    migrated.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall(),
                    [(1,), (2,), (3,), (4,)],
                )
                self.assertEqual(
                    migrated.execute(
                        """
                        SELECT data_type
                        FROM information_schema.columns
                        WHERE table_schema=current_schema()
                          AND table_name='jobs' AND column_name='price'
                        """
                    ).fetchone()[0],
                    "numeric",
                )
                user_columns = {
                    row[0] for row in migrated.execute(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema=current_schema() AND table_name='users'
                        """
                    ).fetchall()
                }
                self.assertTrue({"auth_provider","google_sub","is_blocked"}.issubset(user_columns))
                self.assertTrue(
                    migrated.execute(
                        """
                        SELECT 1 FROM pg_indexes
                        WHERE schemaname=%s
                          AND indexname='idx_payments_click_transaction'
                        """,
                        (self.TARGET_SCHEMA,),
                    ).fetchone()
                )
                self.assertEqual(
                    migrated.execute("SELECT username,balance FROM users WHERE id=17").fetchone(),
                    ("migration-user", Decimal("12345.67")),
                )


if __name__ == "__main__":
    unittest.main()
