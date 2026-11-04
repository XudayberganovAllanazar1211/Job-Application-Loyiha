import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import psycopg

from migrate_sqlite_to_postgres import migrate


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
                        job_id INTEGER UNIQUE,
                        amount REAL,
                        created_at TEXT
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
                },
            ):
                migrate(sqlite_path, "finjob-development")

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


if __name__ == "__main__":
    unittest.main()
