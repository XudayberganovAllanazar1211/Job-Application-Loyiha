"""One-time, guarded SQLite -> Neon PostgreSQL data migration.

Run from the repository root:
  python backend/migrate_sqlite_to_postgres.py --confirm-branch finjob-development

The script refuses production and refuses a non-empty destination database.
"""
import argparse
import datetime
import os
import math
import sqlite3
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import tuple_row

from pg_compat import translate_sql


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_SQLITE_PATH = BACKEND_DIR / "app.db"
EXPECTED_BRANCH = "finjob-development"


def load_environment():
    load_dotenv(PROJECT_DIR / ".env.local", override=False)
    load_dotenv(BACKEND_DIR / ".env", override=False)


def quote_identifier(value):
    return '"' + str(value).replace('"', '""') + '"'


def ensure_development_target(confirm_branch):
    finjob_env = os.environ.get("FINJOB_ENV", "development").strip().lower()
    branch = os.environ.get("NEON_BRANCH", "").strip()
    dsn = os.environ.get("DATABASE_URL", "").strip()

    if finjob_env in {"production", "prod"}:
        raise RuntimeError("Production muhiti uchun migratsiya qat'iyan bloklangan.")
    if branch != EXPECTED_BRANCH or confirm_branch != EXPECTED_BRANCH:
        raise RuntimeError(
            "Faqat finjob-development branchiga migratsiya qilish mumkin. "
            "NEON_BRANCH va --confirm-branch qiymatlarini tekshiring."
        )
    if not dsn.startswith(("postgres://", "postgresql://")):
        raise RuntimeError("DATABASE_URL PostgreSQL DSN bo‘lishi kerak.")
    return dsn


def create_backup(source, sqlite_path):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = sqlite_path.with_name(
        f"{sqlite_path.stem}.pre-postgres-{stamp}{sqlite_path.suffix}"
    )
    backup = sqlite3.connect(str(backup_path))
    try:
        source.backup(backup)
        backup.commit()
    finally:
        backup.close()
    return backup_path


def sqlite_tables(source):
    return source.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()


def sqlite_indexes(source):
    return source.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type='index' AND sql IS NOT NULL
        ORDER BY name
        """
    ).fetchall()


def ensure_target_is_empty(connection):
    tables = connection.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_type = 'BASE TABLE'
          AND table_name <> 'schema_migrations'
        ORDER BY table_name
        """
    ).fetchall()
    if tables:
        names = ", ".join(row[0] for row in tables[:10])
        raise RuntimeError(
            "Neon target bazasi bo‘sh emas. Hech qanday jadval o‘chirilmagan. "
            f"Topilgan jadvallar: {names}"
        )

    migration_ledger = connection.execute(
        """
        SELECT to_regclass(current_schema() || '.schema_migrations')
        """
    ).fetchone()[0]
    if migration_ledger:
        applied = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]
        if applied:
            raise RuntimeError(
                "Neon bazasida avval schema migration yozuvi mavjud. "
                "Target o‘zgartirilmagan; avval holatni tekshiring."
            )


def create_source_tables(connection, tables):
    for table_name, create_sql in tables:
        if not create_sql:
            raise RuntimeError(f"{table_name} jadvali uchun CREATE TABLE SQL topilmadi.")
        connection.execute(translate_sql(create_sql))


def validate_source_columns(source, target, tables):
    for table_name, _ in tables:
        source_columns = [
            row[1] for row in source.execute(
                f"PRAGMA table_info({quote_identifier(table_name)})"
            ).fetchall()
        ]
        target_columns = [
            row[0] for row in target.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table_name,),
            ).fetchall()
        ]
        if source_columns != target_columns:
            raise RuntimeError(
                f"{table_name}: manba va PostgreSQL ustunlari mos emas. "
                f"SQLite={source_columns}; PostgreSQL={target_columns}"
            )


def validate_explicit_indexes(target, indexes):
    actual = {
        row[0] for row in target.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
        ).fetchall()
    }
    missing = [name for name, _ in indexes if name not in actual]
    if missing:
        raise RuntimeError("PostgreSQL indekslari yetishmayapti: " + ", ".join(missing))


def validate_financial_totals(source, target, tables):
    financial_columns = {
        "users": ("balance",),
        "jobs": ("agreed_price",),
        "job_proposals": ("price",),
        "payments": ("amount",),
        "platform_wallet": ("balance", "escrow_balance"),
        "wallet_transactions": ("amount", "balance_after"),
    }
    existing_tables = {name for name, _ in tables}
    checked = []
    for table_name, columns in financial_columns.items():
        if table_name not in existing_tables:
            continue
        source_columns = {
            row[1] for row in source.execute(
                f"PRAGMA table_info({quote_identifier(table_name)})"
            ).fetchall()
        }
        for column in columns:
            if column not in source_columns:
                continue
            quoted_table = quote_identifier(table_name)
            quoted_column = quote_identifier(column)
            source_total = source.execute(
                f"SELECT COALESCE(SUM({quoted_column}), 0) FROM {quoted_table}"
            ).fetchone()[0]
            target_total = target.execute(
                f"SELECT COALESCE(SUM({quoted_column}), 0) FROM {quoted_table}"
            ).fetchone()[0]
            if not math.isclose(
                float(source_total or 0),
                float(target_total or 0),
                rel_tol=0.0,
                abs_tol=0.01,
            ):
                raise RuntimeError(
                    f"{table_name}.{column}: moliyaviy yig‘indi mos kelmadi "
                    f"(SQLite={source_total}, PostgreSQL={target_total})."
                )
            checked.append(f"{table_name}.{column}")
    return checked


def copy_table(source, target, table_name, batch_size=500):
    source_cursor = source.execute(f"SELECT * FROM {quote_identifier(table_name)}")
    column_names = [item[1] for item in source.execute(
        f"PRAGMA table_info({quote_identifier(table_name)})"
    ).fetchall()]
    if not column_names:
        raise RuntimeError(f"{table_name} jadvali ustunlari topilmadi.")

    quoted_columns = ", ".join(quote_identifier(name) for name in column_names)
    placeholders = ", ".join(["%s"] * len(column_names))
    insert_sql = (
        f"INSERT INTO {quote_identifier(table_name)} "
        f"({quoted_columns}) VALUES ({placeholders})"
    )

    copied = 0
    target_cursor = target.cursor()
    try:
        while True:
            rows = source_cursor.fetchmany(batch_size)
            if not rows:
                break
            target_cursor.executemany(insert_sql, rows)
            copied += len(rows)
    finally:
        target_cursor.close()
        source_cursor.close()

    target_count = target.execute(
        f"SELECT COUNT(*) FROM {quote_identifier(table_name)}"
    ).fetchone()[0]
    if target_count != copied:
        raise RuntimeError(
            f"{table_name}: manbada {copied} qator, targetda {target_count} qator."
        )
    return copied


def reset_identity_sequences(source, target, tables):
    for table_name, create_sql in tables:
        if "AUTOINCREMENT" not in (create_sql or "").upper():
            continue
        columns = source.execute(
            f"PRAGMA table_info({quote_identifier(table_name)})"
        ).fetchall()
        id_is_primary_key = any(
            str(row[1]).lower() == "id" and int(row[5] or 0) == 1
            for row in columns
        )
        if not id_is_primary_key:
            continue

        sequence_name = target.execute(
            "SELECT pg_get_serial_sequence(%s, 'id')",
            (table_name,),
        ).fetchone()[0]
        if not sequence_name:
            continue

        max_id = target.execute(
            f"SELECT MAX(id) FROM {quote_identifier(table_name)}"
        ).fetchone()[0]
        if max_id is None:
            target.execute("SELECT setval(%s, 1, false)", (sequence_name,))
        else:
            target.execute("SELECT setval(%s, %s, true)", (sequence_name, max_id))


def record_schema_version(target):
    target.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations(
            version BIGINT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    target.execute(
        """
        INSERT INTO schema_migrations(version, name, applied_at)
        VALUES (%s, %s, %s)
        """,
        (
            1,
            "initial_schema_imported_from_sqlite",
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ),
    )


def migrate(sqlite_path, confirm_branch):
    dsn = ensure_development_target(confirm_branch)
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite bazasi topilmadi: {sqlite_path}")

    integrity = sqlite3.connect(
        sqlite_path.resolve().as_uri() + "?mode=ro", uri=True
    )
    try:
        integrity_result = integrity.execute("PRAGMA integrity_check").fetchone()
        if not integrity_result or integrity_result[0] != "ok":
            raise RuntimeError("SQLite bazasi integrity_check tekshiruvidan o‘tmadi.")

        tables = sqlite_tables(integrity)
        indexes = sqlite_indexes(integrity)
        if not tables:
            raise RuntimeError("SQLite bazasida ko‘chiriladigan jadvallar topilmadi.")

        backup_path = create_backup(integrity, sqlite_path)
        print(f"SQLite backup yaratildi: {backup_path.name}")
        print(f"Ko‘chiriladigan jadvallar: {len(tables)}")
        print(f"Ko‘chiriladigan explicit indekslar: {len(indexes)}")

        with psycopg.connect(
            dsn,
            connect_timeout=15,
            row_factory=tuple_row,
            application_name="finjob-sqlite-migration",
        ) as target:
            ensure_target_is_empty(target)
            target.execute("SET lock_timeout = '15s'")
            target.execute("SET statement_timeout = '10min'")

            copied_counts = {}
            try:
                create_source_tables(target, tables)
                validate_source_columns(integrity, target, tables)

                for table_name, _ in tables:
                    copied_counts[table_name] = copy_table(
                        integrity, target, table_name
                    )

                for index_name, index_sql in indexes:
                    target.execute(translate_sql(index_sql))
                validate_explicit_indexes(target, indexes)
                checked_financial_columns = validate_financial_totals(
                    integrity, target, tables
                )

                reset_identity_sequences(integrity, target, tables)
                record_schema_version(target)

                for table_name, expected_count in copied_counts.items():
                    actual_count = target.execute(
                        f"SELECT COUNT(*) FROM {quote_identifier(table_name)}"
                    ).fetchone()[0]
                    if actual_count != expected_count:
                        raise RuntimeError(
                            f"{table_name}: yakuniy row-count mos kelmadi."
                        )
                target.commit()
            except Exception:
                target.rollback()
                raise

        print("Migratsiya muvaffaqiyatli yakunlandi.")
        print(f"Jadvallar: {len(copied_counts)}")
        print(f"Indekslar: {len(indexes)}")
        print(f"Jami qatorlar: {sum(copied_counts.values())}")
        print(f"Tekshirilgan moliyaviy ustunlar: {len(checked_financial_columns)}")
        print("Target: finjob-development (production o‘zgartirilmadi).")
    finally:
        integrity.close()


def main():
    load_environment()
    parser = argparse.ArgumentParser(description="SQLite -> Neon PostgreSQL migration")
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=DEFAULT_SQLITE_PATH,
        help="SQLite source file (default: backend/app.db)",
    )
    parser.add_argument(
        "--confirm-branch",
        required=True,
        help="Must be exactly finjob-development.",
    )
    args = parser.parse_args()

    try:
        migrate(args.sqlite.resolve(), args.confirm_branch.strip())
    except Exception as exc:
        print(f"MIGRATION FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
