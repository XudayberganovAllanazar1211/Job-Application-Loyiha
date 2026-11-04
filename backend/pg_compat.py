"""Small SQLite-API compatibility layer backed by PostgreSQL/Neon.

The application keeps its existing DB-API call shape while SQL is translated
at the database boundary. New database code should prefer native PostgreSQL SQL.
"""
import os
import re
from decimal import Decimal

import psycopg
from psycopg.rows import tuple_row


IntegrityError = psycopg.IntegrityError

_AUTO_ID_TABLES = {
    "admin_audit_log", "appeals", "disputes", "favorites",
    "job_proposals", "job_services", "jobs", "messages",
    "notifications", "payments", "portfolio_items", "ratings",
    "recently_viewed", "reports", "saved_searches", "services",
    "user_blocks", "users", "wallet_transactions",
}


def _replace_qmark_placeholders(sql):
    """Translate SQLite ? placeholders without changing quoted strings/comments."""
    result = []
    index = 0
    state = "normal"
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if state == "normal":
            if char == "'":
                state = "single"
                result.append(char)
            elif char == '"':
                state = "double"
                result.append(char)
            elif char == "-" and next_char == "-":
                state = "line_comment"
                result.extend((char, next_char))
                index += 1
            elif char == "/" and next_char == "*":
                state = "block_comment"
                result.extend((char, next_char))
                index += 1
            elif char == "?":
                result.append("%s")
            else:
                result.append(char)
        elif state == "single":
            result.append(char)
            if char == "'" and next_char == "'":
                result.append(next_char)
                index += 1
            elif char == "'":
                state = "normal"
        elif state == "double":
            result.append(char)
            if char == '"' and next_char == '"':
                result.append(next_char)
                index += 1
            elif char == '"':
                state = "normal"
        elif state == "line_comment":
            result.append(char)
            if char == "\n":
                state = "normal"
        elif state == "block_comment":
            result.append(char)
            if char == "*" and next_char == "/":
                result.append(next_char)
                index += 1
                state = "normal"
        index += 1
    return "".join(result)


_MONEY_SQL_PATTERN = re.compile(
    r"\b(balance|escrow_balance|amount|balance_after|agreed_price|price)\b",
    flags=re.IGNORECASE,
)


def _adapt_money_params(sql, params):
    """Bind monetary Python floats as Decimal/numeric, not float8."""
    if params is None or not _MONEY_SQL_PATTERN.search(sql):
        return params
    if isinstance(params, dict):
        return {
            key: Decimal(str(value)) if isinstance(value, float) else value
            for key, value in params.items()
        }
    return tuple(
        Decimal(str(value)) if isinstance(value, float) else value
        for value in params
    )


def translate_sql(sql):
    """Translate the SQLite SQL subset retained by the current Flask application."""
    if not isinstance(sql, str):
        raise TypeError("SQL query must be a string")
    query = sql.strip()
    if not query:
        return query

    table_info = re.fullmatch(
        r"""PRAGMA\s+table_info\s*\(\s*['"]?([A-Za-z_][A-Za-z0-9_]*)['"]?\s*\)\s*;?""",
        query,
        flags=re.IGNORECASE,
    )
    if table_info:
        return (
            "SELECT c.ordinal_position - 1 AS cid, c.column_name AS name, "
            "CASE WHEN c.data_type = 'USER-DEFINED' THEN c.udt_name "
            "ELSE c.data_type END AS type, "
            "CASE WHEN c.is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull, "
            "c.column_default AS dflt_value, "
            "CASE WHEN EXISTS ("
            "SELECT 1 FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "ON tc.constraint_catalog = kcu.constraint_catalog "
            "AND tc.constraint_schema = kcu.constraint_schema "
            "AND tc.constraint_name = kcu.constraint_name "
            "WHERE tc.table_schema = c.table_schema "
            "AND tc.table_name = c.table_name "
            "AND tc.constraint_type = 'PRIMARY KEY' "
            "AND kcu.column_name = c.column_name"
            ") THEN 1 ELSE 0 END AS pk "
            "FROM information_schema.columns c "
            "WHERE c.table_schema = current_schema() AND c.table_name = %s "
            "ORDER BY c.ordinal_position"
        )

    sqlite_master = re.fullmatch(
        r"SELECT\s+name\s+FROM\s+sqlite_master\s+WHERE\s+type\s*=\s*'table'\s+AND\s+name\s*=\s*'([A-Za-z_][A-Za-z0-9_]*)'\s*;?",
        query,
        flags=re.IGNORECASE,
    )
    if sqlite_master:
        table = sqlite_master.group(1).lower()
        return (
            "SELECT table_name AS name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE' "
            f"AND table_name = '{table}'"
        )
    if "sqlite_master" in query.lower():
        raise NotImplementedError(
            "Bu sqlite_master so‘rovi PostgreSQL uchun alohida moslashtirilishi kerak."
        )

    ignore_insert = bool(
        re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", query, flags=re.IGNORECASE)
    )
    query = re.sub(
        r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
        "INSERT INTO",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\bIS\s+\?", "IS NOT DISTINCT FROM ?", query, flags=re.IGNORECASE)
    query = re.sub(r"\bGROUP_CONCAT\s*\(", "STRING_AGG(", query, flags=re.IGNORECASE)
    query = re.sub(r"\bLIKE\b", "ILIKE", query, flags=re.IGNORECASE)
    query = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\b",
        "BIGINT PRIMARY KEY",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\bREAL\b", "DOUBLE PRECISION", query, flags=re.IGNORECASE)
    query = re.sub(r"(\bprice\s+)INTEGER\b", r"\1NUMERIC(18,2)", query, flags=re.IGNORECASE)

    for column in (
        "balance", "escrow_balance", "amount", "balance_after",
        "agreed_price", "price",
    ):
        query = re.sub(
            rf"(\b{column}\s+)DOUBLE\s+PRECISION\b",
            r"\1NUMERIC(18,2)",
            query,
            flags=re.IGNORECASE,
        )

    query = _replace_qmark_placeholders(query)
    if ignore_insert and "ON CONFLICT" not in query.upper():
        query = query.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return query


class PostgreSQLCursor:
    def __init__(self, raw_cursor):
        self._cursor = raw_cursor
        self._auto_returning = False
        self._lastrowid_loaded = False
        self._lastrowid = None
        self._prefetched_row = None

    def execute(self, sql, params=None):
        # A cursor may be reused for many statements; do not leak RETURNING
        # state or a prefetched row from the previous statement.
        self._auto_returning = False
        self._lastrowid_loaded = False
        self._lastrowid = None
        self._prefetched_row = None

        query = translate_sql(sql)
        pragma_match = re.fullmatch(
            r"""PRAGMA\s+table_info\s*\(\s*['"]?([A-Za-z_][A-Za-z0-9_]*)['"]?\s*\)\s*;?""",
            str(sql).strip(),
            flags=re.IGNORECASE,
        )
        if pragma_match:
            params = (pragma_match.group(1),)
        else:
            insert_match = re.match(
                r"\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)",
                query,
                flags=re.IGNORECASE,
            )
            if (
                insert_match
                and insert_match.group(1).lower() in _AUTO_ID_TABLES
                and "RETURNING" not in query.upper()
            ):
                query = query.rstrip().rstrip(";") + " RETURNING id"
                self._auto_returning = True
        adapted_params = _adapt_money_params(query, params)
        self._cursor.execute(query, adapted_params if adapted_params is not None else ())
        return self

    def executemany(self, sql, params_seq):
        query = translate_sql(sql)
        if "RETURNING" in query.upper():
            raise ValueError("executemany bilan RETURNING ishlatilmaydi.")
        adapted_params = [
            _adapt_money_params(query, params) for params in params_seq
        ]
        self._cursor.executemany(query, adapted_params)
        return self

    def fetchone(self):
        if self._prefetched_row is not None:
            row = self._prefetched_row
            self._prefetched_row = None
            return row
        return self._cursor.fetchone()

    def fetchmany(self, size=None):
        rows = self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
        if self._prefetched_row is not None:
            rows = [self._prefetched_row, *rows]
            self._prefetched_row = None
        return rows

    def fetchall(self):
        rows = self._cursor.fetchall()
        if self._prefetched_row is not None:
            rows = [self._prefetched_row, *rows]
            self._prefetched_row = None
        return rows

    @property
    def lastrowid(self):
        if not self._auto_returning:
            return None
        if not self._lastrowid_loaded:
            row = self._cursor.fetchone()
            self._lastrowid = row[0] if row else None
            self._prefetched_row = row
            self._lastrowid_loaded = True
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        self._cursor.close()


class PostgreSQLConnection:
    def __init__(self, raw_connection):
        self._connection = raw_connection

    def cursor(self):
        return PostgreSQLCursor(self._connection.cursor())

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def executemany(self, sql, params_seq):
        return self.cursor().executemany(sql, params_seq)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    @property
    def closed(self):
        return self._connection.closed

    def __getattr__(self, name):
        return getattr(self._connection, name)


def connect(database=None, check_same_thread=False, timeout=15.0, **kwargs):
    """Open a PostgreSQL connection using DATABASE_URL or an explicit DSN."""
    dsn = database or os.environ.get("DATABASE_URL", "").strip()
    if not dsn or "://" not in dsn:
        raise RuntimeError(
            "DATABASE_URL PostgreSQL DSN majburiy. SQLite fallback ataylab o‘chirilgan."
        )
    connect_timeout = max(1, int(float(timeout)))
    raw = psycopg.connect(
        dsn,
        connect_timeout=connect_timeout,
        row_factory=tuple_row,
        application_name="finjob",
        prepare_threshold=None,
        **kwargs,
    )
    return PostgreSQLConnection(raw)
