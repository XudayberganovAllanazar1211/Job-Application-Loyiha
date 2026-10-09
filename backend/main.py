import os
import re
import math
import time
import threading
import sqlite3
import datetime
import secrets
import smtplib
import uuid
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as URLRequest, urlopen
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps, UnidentifiedImageError
from payments import register_payment_routes
import jwt

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
finjob_env = os.environ.get("FINJOB_ENV", "development").strip().lower()
is_production = finjob_env in {"production", "prod"}
raw_cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174")
allowed_origins = [origin.strip().rstrip("/") for origin in raw_cors_origins.split(",") if origin.strip()]
if is_production and "*" in allowed_origins:
    raise RuntimeError("Production muhitida CORS_ORIGINS wildcard (*) bo‘lishi mumkin emas.")
CORS(app, resources={r"/*": {"origins": allowed_origins, "supports_credentials": False}})
secret_key = os.environ.get("SECRET_KEY", "").strip()
if not secret_key:
    if is_production:
        raise RuntimeError("Production muhitida SECRET_KEY environment o‘zgaruvchisi majburiy.")
    secret_key = secrets.token_hex(32)
    app.logger.warning("SECRET_KEY o‘rnatilmagan; development uchun vaqtinchalik kalit ishlatilmoqda.")
app.config["SECRET_KEY"] = secret_key
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
try:
    app.config["JWT_TTL_HOURS"] = max(1, min(24, int(os.environ.get("JWT_TTL_HOURS", "12"))))
except (TypeError, ValueError):
    app.config["JWT_TTL_HOURS"] = 12


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    if response.content_type and response.content_type.startswith("application/json"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    if request.is_secure or os.environ.get("FORCE_HTTPS") == "1":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# -------- RATE LIMITING --------
_rate_buckets = {}
_rate_lock = threading.Lock()
_RATE_LIMIT_RULES = {
    "/login": (10, 60),
    "/auth/google": (10, 60),
    "/register/send-code": (3, 900),
    "/register/verify": (10, 900),
    "/forgot-password/send-code": (3, 900),
    "/forgot-password/reset": (10, 900),
    "/message": (60, 60),
    "/report": (10, 600),
    "/rating": (20, 600),
    "/job": (20, 60),
    "/favorites": (120, 60),
    "/profile/avatar": (5, 300),
    "/portfolio/upload": (5, 300),
    "/proposals/": (60, 60),
    "/portfolio/": (60, 60),
    "/wallet/withdraw": (10, 600),
    "/payments/create/": (10, 60),
    "/payments/dummy/": (10, 60),
    "/reverse-geocode": (20, 60),
    "/saved-searches/": (30, 600),
    "/recently-viewed/": (60, 60),
    "/disputes": (10, 600),
    "/disputes/": (30, 600),
}


def _rate_limit_key(path):
    ip = request.remote_addr or "unknown"
    extra = ""
    payload = request.get_json(silent=True) or {}
    if path == "/login":
        extra = ":" + str(payload.get("username", "")).strip().lower()[:254]
    elif path in ("/register/send-code", "/register/verify", "/forgot-password/send-code", "/forgot-password/reset"):
        extra = ":" + str(payload.get("email", "")).strip().lower()[:254]
    return f"{path}:{ip}{extra}"


def _rate_limited(path):
    rule = _RATE_LIMIT_RULES.get(path)
    if rule is None:
        rule = next((value for prefix, value in _RATE_LIMIT_RULES.items() if prefix.endswith("/") and path.startswith(prefix)), None)
    if rule is None:
        return False, 0
    limit, window = rule
    now = time.monotonic()
    key = _rate_limit_key(path)
    with _rate_lock:
        bucket = _rate_buckets.setdefault(key, [])
        cutoff = now - window
        while bucket and bucket[0] <= cutoff:
            bucket.pop(0)
        if len(bucket) >= limit:
            retry_after = max(1, int(window - (now - bucket[0])))
            return True, retry_after
        bucket.append(now)
        if len(_rate_buckets) > 5000:
            stale_cutoff = now - 3600
            stale_keys = [k for k, values in _rate_buckets.items() if not values or values[-1] < stale_cutoff]
            for stale_key in stale_keys[:1000]:
                _rate_buckets.pop(stale_key, None)
    return False, 0


@app.before_request
def apply_rate_limits():
    if request.method == "OPTIONS":
        return None
    if request.method in {"POST", "PATCH", "DELETE"}:
        blocked, retry_after = _rate_limited(request.path)
    elif request.method == "GET" and request.path == "/reverse-geocode":
        blocked, retry_after = _rate_limited(request.path)
    else:
        blocked, retry_after = False, 0
    if blocked:
        response = jsonify({"msg": "Juda ko‘p so‘rov yuborildi. Birozdan keyin qayta urinib ko‘ring."})
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response
    return None

# -------- E-MAIL (SMTP) SOZLAMALARI --------
SMTP_SERVER = os.environ.get("MAIL_SERVER") or os.environ.get("SMTP_SERVER", "smtp.gmail.com")
try:
    SMTP_PORT = int(os.environ.get("MAIL_PORT") or os.environ.get("SMTP_PORT", "587"))
except (TypeError, ValueError):
    SMTP_PORT = 587
SMTP_USER = os.environ.get("MAIL_USERNAME") or os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("MAIL_PASSWORD") or os.environ.get("SMTP_PASSWORD", "")
SMTP_USE_TLS = str(os.environ.get("MAIL_USE_TLS", os.environ.get("SMTP_USE_TLS", "True"))).strip().lower() in {"1", "true", "yes", "on"}
SMTP_USE_SSL = str(os.environ.get("MAIL_USE_SSL", os.environ.get("SMTP_USE_SSL", "False"))).strip().lower() in {"1", "true", "yes", "on"}

pending_verifications = {}
pending_password_resets = {}

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def send_auth_code_email(to_email, code, purpose="register"):
    if purpose == "reset":
        subject = "FinJob — Parolni tiklash kodi"
        title = "Parolni tiklash"
        intro = "FinJob hisobingiz uchun parolni tiklash so‘rovi qabul qilindi."
    else:
        subject = "FinJob — Elektron pochtani tasdiqlash kodi"
        title = "Email manzilini tasdiqlash"
        intro = "FinJob hisobingizni ro‘yxatdan o‘tkazishni yakunlash uchun quyidagi koddan foydalaning."

    text_body = (
        f"{intro}\n\n"
        f"Tasdiqlash kodi: {code}\n\n"
        "Kod 10 daqiqa amal qiladi. Agar bu so‘rovni siz yubormagan bo‘lsangiz, "
        "ushbu xatni e’tiborsiz qoldiring. Kodni hech kimga bermang."
    )
    html_body = f"""<!doctype html>
<html lang="uz">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f4f7fb;font-family:Arial,sans-serif;color:#172033;">
  <div style="max-width:560px;margin:32px auto;padding:0 16px;">
    <div style="background:#111827;border-radius:18px 18px 0 0;padding:24px;color:white;">
      <div style="font-size:24px;font-weight:800;">FinJob</div>
      <div style="margin-top:6px;opacity:.8;">Ish toping. Ishni yakunlang.</div>
    </div>
    <div style="background:white;border:1px solid #e5e7eb;border-top:0;border-radius:0 0 18px 18px;padding:32px;">
      <h1 style="font-size:22px;margin:0 0 12px;">{title}</h1>
      <p style="font-size:15px;line-height:1.6;color:#4b5563;">{intro}</p>
      <div style="margin:26px 0;text-align:center;background:#f3f4f6;border-radius:14px;padding:20px;">
        <div style="font-size:12px;color:#6b7280;margin-bottom:8px;">6 xonali kod</div>
        <div style="font-size:34px;letter-spacing:8px;font-weight:800;">{code}</div>
      </div>
      <p style="font-size:13px;line-height:1.6;color:#6b7280;">
        Kod 10 daqiqa amal qiladi. Agar bu so‘rovni siz yubormagan bo‘lsangiz, xatni e’tiborsiz qoldiring.
      </p>
      <p style="font-size:13px;color:#9ca3af;margin:24px 0 0;">Bu avtomatik xat. Iltimos, unga javob bermang.</p>
    </div>
  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = SMTP_USER
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if not SMTP_USER or not SMTP_PASSWORD:
            app.logger.error("SMTP credentials sozlanmagan.")
            return False
        if SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=15)
        else:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15)
        with server:
            server.ehlo()
            if SMTP_USE_TLS:
                server.starttls()
                server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception as e:
        app.logger.exception("Email yuborishda xatolik yuz berdi: %s", e)
        return False


def send_email_code(to_email, code):
    return send_auth_code_email(to_email, code, "register")


# -------- DATABASE --------
class DB:
    def __init__(self, db_name="app.db"):
        self.db_name = db_name
        self.init()
        self.seed()

    def get_connection(self):
        conn = sqlite3.connect(self.db_name, check_same_thread=False, timeout=15.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA cache_size = -32768;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA mmap_size = 268435456;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _query_connection(self):
        local = getattr(threading.current_thread(), "_finjob_db", None)
        if local is None or local.get("db_name") != self.db_name:
            local = {"db_name": self.db_name, "conn": self.get_connection()}
            setattr(threading.current_thread(), "_finjob_db", local)
        return local["conn"]

    def init(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                first_name TEXT,
                last_name TEXT,
                birthday TEXT,
                email TEXT UNIQUE,
                bio TEXT DEFAULT '',
                skills TEXT DEFAULT '',
                created_at TEXT,
                average_rating REAL DEFAULT 0.0,
                role TEXT DEFAULT 'user',
                avatar_url TEXT DEFAULT '',
                token_version INTEGER NOT NULL DEFAULT 0,
                balance REAL DEFAULT 0,
                last_seen_at TEXT DEFAULT ''
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS services(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                parent_id INTEGER,
                created_by INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                service_id INTEGER,
                title TEXT,
                description TEXT,
                price INTEGER,
                currency TEXT DEFAULT 'UZS',
                location TEXT,
                worker_id INTEGER,
                status TEXT,
                created_at TEXT,
                finished_at TEXT,
                custom_service TEXT DEFAULT '',
                agreed_price REAL
            )
        """)

        job_columns = [row[1] for row in cursor.execute("PRAGMA table_info(jobs)").fetchall()]
        if "owner_finished" not in job_columns:
            cursor.execute("ALTER TABLE jobs ADD COLUMN owner_finished INTEGER NOT NULL DEFAULT 0")
        if "worker_finished" not in job_columns:
            cursor.execute("ALTER TABLE jobs ADD COLUMN worker_finished INTEGER NOT NULL DEFAULT 0")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_services(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                service_id INTEGER,
                custom_service TEXT DEFAULT ''
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ratings(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                from_user INTEGER,
                to_user INTEGER,
                score INTEGER,
                comment TEXT,
                created_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                link TEXT DEFAULT '',
                is_read INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id INTEGER NOT NULL,
                reported_user_id INTEGER,
                job_id INTEGER,
                reason TEXT NOT NULL,
                details TEXT DEFAULT '',
                status TEXT DEFAULT 'open',
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER,
                receiver_id INTEGER,
                job_id INTEGER,
                message TEXT,
                sent_at TEXT,
                read_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_proposals(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                worker_id INTEGER NOT NULL,
                price REAL NOT NULL,
                deadline TEXT NOT NULL,
                message TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(job_id, worker_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorites(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, target_type, target_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                url TEXT DEFAULT '',
                image_url TEXT DEFAULT '',
                file_url TEXT DEFAULT '',
                file_name TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_searches(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                filters TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, name)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recently_viewed(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                job_id INTEGER NOT NULL,
                viewed_at TEXT NOT NULL,
                UNIQUE(user_id, job_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS typing_states(
                job_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(job_id, user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_uuid TEXT UNIQUE NOT NULL,
                job_id INTEGER NOT NULL UNIQUE,
                payer_id INTEGER NOT NULL,
                payee_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'UZS',
                provider TEXT NOT NULL DEFAULT 'click',
                status TEXT NOT NULL DEFAULT 'pending',
                provider_transaction_id TEXT DEFAULT '',
                provider_prepare_id TEXT DEFAULT '',
                provider_payload TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                paid_at TEXT,
                released_at TEXT,
                refunded_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wallet_transactions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                balance_after REAL NOT NULL,
                job_id INTEGER,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS platform_wallet(
                id INTEGER PRIMARY KEY CHECK(id=1),
                balance REAL NOT NULL DEFAULT 0,
                escrow_balance REAL NOT NULL DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS platform_settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        try:
            initial_commission = float(os.environ.get("FINJOB_COMMISSION_PERCENT", "10"))
        except (TypeError, ValueError):
            initial_commission = 10.0
        initial_commission = max(0.0, min(100.0, initial_commission))
        cursor.execute(
            "INSERT OR IGNORE INTO platform_settings(key,value) VALUES('commission_percent',?)",
            (str(round(initial_commission, 2)),)
        )
        cursor.execute("INSERT OR IGNORE INTO platform_wallet(id,balance,escrow_balance) VALUES(1,0,0)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS disputes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                opened_by INTEGER NOT NULL,
                against_user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                evidence TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                admin_response TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                resolved_at TEXT,
                resolved_by INTEGER,
                decision TEXT NOT NULL DEFAULT '',
                decision_for_user_id INTEGER,
                payment_action TEXT NOT NULL DEFAULT 'none',
                job_action TEXT NOT NULL DEFAULT 'none',
                sanction_user_id INTEGER,
                sanction_type TEXT NOT NULL DEFAULT 'none',
                sanction_duration_minutes INTEGER
            )
        """)
        cursor.execute("PRAGMA table_info(disputes)")
        existing_dispute_cols = [row[1] for row in cursor.fetchall()]
        dispute_migrations = [
            ("decision", "ALTER TABLE disputes ADD COLUMN decision TEXT NOT NULL DEFAULT ''"),
            ("decision_for_user_id", "ALTER TABLE disputes ADD COLUMN decision_for_user_id INTEGER"),
            ("payment_action", "ALTER TABLE disputes ADD COLUMN payment_action TEXT NOT NULL DEFAULT 'none'"),
            ("job_action", "ALTER TABLE disputes ADD COLUMN job_action TEXT NOT NULL DEFAULT 'none'"),
            ("sanction_user_id", "ALTER TABLE disputes ADD COLUMN sanction_user_id INTEGER"),
            ("sanction_type", "ALTER TABLE disputes ADD COLUMN sanction_type TEXT NOT NULL DEFAULT 'none'"),
            ("sanction_duration_minutes", "ALTER TABLE disputes ADD COLUMN sanction_duration_minutes INTEGER"),
        ]
        for col_name, sql in dispute_migrations:
            if col_name not in existing_dispute_cols:
                try:
                    cursor.execute(sql)
                except Exception:
                    pass
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_disputes_job_status ON disputes(job_id,status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_disputes_opened_by ON disputes(opened_by,created_at DESC)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT DEFAULT '',
                target_id INTEGER,
                details TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_log(created_at DESC)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_blocks(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                block_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                duration_minutes INTEGER,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER NOT NULL,
                lifted_at TEXT,
                lifted_by INTEGER
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_blocks_user_active ON user_blocks(user_id,active,expires_at)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appeals(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                block_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                appeal_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                admin_response TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewed_by INTEGER
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_appeals_status_created ON appeals(status,created_at)")

        # Dynamic migrations for any existing tables missing new columns
        cursor.execute("PRAGMA table_info(users)")
        existing_user_cols = [row[1] for row in cursor.fetchall()]
        migrations = [
            ("bio", "ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''"),
            ("skills", "ALTER TABLE users ADD COLUMN skills TEXT DEFAULT ''"),
            ("created_at", "ALTER TABLE users ADD COLUMN created_at TEXT"),
            ("average_rating", "ALTER TABLE users ADD COLUMN average_rating REAL DEFAULT 0.0"),
            ("role", "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'"),
            ("avatar_url", "ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT ''"),
            ("token_version", "ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"),
            ("balance", "ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0"),
            ("last_seen_at", "ALTER TABLE users ADD COLUMN last_seen_at TEXT DEFAULT ''"),
            ("email_verified", "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1"),
            ("phone_verified", "ALTER TABLE users ADD COLUMN phone_verified INTEGER NOT NULL DEFAULT 0"),
            ("identity_verified", "ALTER TABLE users ADD COLUMN identity_verified INTEGER NOT NULL DEFAULT 0"),
            ("verification_updated_at", "ALTER TABLE users ADD COLUMN verification_updated_at TEXT DEFAULT ''"),
            ("is_blocked", "ALTER TABLE users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0"),
            ("auth_provider", "ALTER TABLE users ADD COLUMN auth_provider TEXT DEFAULT 'password'"),
            ("google_sub", "ALTER TABLE users ADD COLUMN google_sub TEXT DEFAULT ''"),
        ]
        for col_name, sql in migrations:
            if col_name not in existing_user_cols:
                try:
                    cursor.execute(sql)
                except Exception:
                    pass

        cursor.execute("PRAGMA table_info(jobs)")
        existing_job_cols = [row[1] for row in cursor.fetchall()]
        if "currency" not in existing_job_cols:
            try:
                cursor.execute("ALTER TABLE jobs ADD COLUMN currency TEXT DEFAULT 'UZS'")
            except Exception:
                pass

        if "custom_service" not in existing_job_cols:
            try:
                cursor.execute("ALTER TABLE jobs ADD COLUMN custom_service TEXT DEFAULT ''")
            except Exception:
                pass

        if "agreed_price" not in existing_job_cols:
            try:
                cursor.execute("ALTER TABLE jobs ADD COLUMN agreed_price REAL")
            except Exception:
                pass

        if "finished_at" not in existing_job_cols:
            try:
                cursor.execute("ALTER TABLE jobs ADD COLUMN finished_at TEXT")
            except Exception:
                pass

        # Active ish hech qachon biriktirilgan bajaruvchiga ega bo‘lmasligi kerak.
        # Eski bazadagi active + worker_id holatini avtomatik tiklaymiz.
        try:
            cursor.execute(
                "UPDATE jobs SET worker_id=NULL WHERE status='active' AND worker_id IS NOT NULL"
            )
        except Exception:
            pass

        cursor.execute("PRAGMA table_info(ratings)")
        existing_rating_cols = [row[1] for row in cursor.fetchall()]
        cursor.execute("PRAGMA table_info(messages)")
        existing_message_cols = [row[1] for row in cursor.fetchall()]
        if "read_at" not in existing_message_cols:
            try:
                cursor.execute("ALTER TABLE messages ADD COLUMN read_at TEXT")
            except Exception:
                pass
        if "attachment_url" not in existing_message_cols:
            try:
                cursor.execute("ALTER TABLE messages ADD COLUMN attachment_url TEXT DEFAULT ''")
            except Exception:
                pass
        if "attachment_name" not in existing_message_cols:
            try:
                cursor.execute("ALTER TABLE messages ADD COLUMN attachment_name TEXT DEFAULT ''")
            except Exception:
                pass
        if "attachment_type" not in existing_message_cols:
            try:
                cursor.execute("ALTER TABLE messages ADD COLUMN attachment_type TEXT DEFAULT ''")
            except Exception:
                pass

        cursor.execute("PRAGMA table_info(reports)")
        existing_report_cols = [row[1] for row in cursor.fetchall()]
        if "message_id" not in existing_report_cols:
            try:
                cursor.execute("ALTER TABLE reports ADD COLUMN message_id INTEGER")
            except Exception:
                pass
        report_migrations = [
            ("admin_response", "ALTER TABLE reports ADD COLUMN admin_response TEXT DEFAULT ''"),
            ("decision", "ALTER TABLE reports ADD COLUMN decision TEXT DEFAULT ''"),
            ("payment_action", "ALTER TABLE reports ADD COLUMN payment_action TEXT NOT NULL DEFAULT 'none'"),
            ("job_action", "ALTER TABLE reports ADD COLUMN job_action TEXT NOT NULL DEFAULT 'none'"),
            ("notify_target", "ALTER TABLE reports ADD COLUMN notify_target TEXT NOT NULL DEFAULT 'none'"),
            ("sanction_user_id", "ALTER TABLE reports ADD COLUMN sanction_user_id INTEGER"),
            ("sanction_type", "ALTER TABLE reports ADD COLUMN sanction_type TEXT NOT NULL DEFAULT 'none'"),
            ("sanction_duration_minutes", "ALTER TABLE reports ADD COLUMN sanction_duration_minutes INTEGER"),
        ]
        for col_name, sql in report_migrations:
            if col_name not in existing_report_cols:
                try:
                    cursor.execute(sql)
                except Exception:
                    pass

        if "created_at" not in existing_rating_cols:
            try:
                cursor.execute("ALTER TABLE ratings ADD COLUMN created_at TEXT")
            except Exception:
                pass

        cursor.execute("PRAGMA table_info(portfolio_items)")
        existing_portfolio_cols = [row[1] for row in cursor.fetchall()]
        portfolio_migrations = [
            ("file_url", "ALTER TABLE portfolio_items ADD COLUMN file_url TEXT DEFAULT ''"),
            ("file_name", "ALTER TABLE portfolio_items ADD COLUMN file_name TEXT DEFAULT ''"),
        ]
        for col_name, sql in portfolio_migrations:
            if col_name not in existing_portfolio_cols:
                try:
                    cursor.execute(sql)
                except Exception:
                    pass

        # Database Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_rating ON users(average_rating DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_status ON jobs(user_id, status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_worker_status ON jobs(worker_id, status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_service ON jobs(service_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at DESC, id DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_service_status_created ON jobs(service_id, status, created_at DESC, id DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_services_parent_name ON services(parent_id, name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_job ON messages(job_id, sent_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_job_id_desc ON messages(job_id, id DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_receiver_read ON messages(receiver_id, read_at, sent_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender_sent ON messages(sender_id, sent_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_proposals_job_status ON job_proposals(job_id, status, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_proposals_worker_status ON job_proposals(worker_id, status, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_favorites_user_target ON favorites(user_id, target_type, target_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_user_created ON portfolio_items(user_id, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_payer_status ON payments(payer_id,status,created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_payee_status ON payments(payee_id,status,created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_job_status ON payments(job_id,status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user ON wallet_transactions(user_id,created_at);")
        duplicate_ratings = cursor.execute(
            """SELECT job_id,from_user,MIN(id)
               FROM ratings
               WHERE job_id IS NOT NULL AND from_user IS NOT NULL
               GROUP BY job_id,from_user
               HAVING COUNT(*)>1"""
        ).fetchall()
        for duplicate_job_id, duplicate_from_user, keep_id in duplicate_ratings:
            cursor.execute(
                "DELETE FROM ratings WHERE job_id=? AND from_user=? AND id!=?",
                (duplicate_job_id, duplicate_from_user, keep_id),
            )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ratings_job_from_user ON ratings(job_id,from_user)"
        )
        cursor.execute(
            "UPDATE users SET average_rating=COALESCE((SELECT ROUND(AVG(score),1) FROM ratings WHERE to_user=users.id),0)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ratings_to_user ON ratings(to_user);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ratings_job ON ratings(job_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_saved_searches_user_updated ON saved_searches(user_id, updated_at DESC, id DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recently_viewed_user_viewed ON recently_viewed(user_id, viewed_at DESC, id DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_services_service_job ON job_services(service_id, job_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_location_status_created ON jobs(location, status, created_at DESC, id DESC);")

        conn.commit()
        conn.close()

    def seed(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        catalog = {
            "Dasturlash": {
                "Backend": [
                    "Python Backend", "Django", "Flask", "FastAPI", "Node.js", "Express.js",
                    "REST API", "GraphQL", "Microservices", "WebSocket", "API Integration",
                    "Database Backend", "Authentication", "Payment Integration"
                ],
                "Frontend": [
                    "HTML/CSS", "JavaScript", "React", "Vue.js", "Angular", "Next.js",
                    "UI Development", "Responsive Web", "Landing Page", "Figma to HTML",
                    "Frontend Bug Fix", "Animation", "Tailwind CSS"
                ],
                "Mobile": [
                    "Android", "iOS", "Flutter", "React Native", "Kotlin", "Swift",
                    "Mobile UI", "Mobile Bug Fix"
                ],
                "Desktop": [
                    "Desktop App", "C++ App", "C# App", "Java App", "Electron"
                ],
                "Game Development": [
                    "Unity", "Unreal Engine", "Godot", "Roblox Development",
                    "2D Game", "3D Game", "Game Bug Fix"
                ],
                "Automation": [
                    "Python Automation", "Web Scraping", "Browser Automation",
                    "Data Processing", "Excel Automation", "Bot Automation"
                ]
            },
            "Dizayn": {
                "UI/UX": [
                    "Website UI/UX", "Mobile UI/UX", "Dashboard Design",
                    "Wireframe", "Prototype", "Design System"
                ],
                "Grafik": [
                    "Logo Design", "Banner Design", "Poster Design", "Social Media Design",
                    "Presentation Design", "Business Card", "Illustration", "Infographic"
                ],
                "3D": [
                    "3D Modeling", "3D Product Design", "Blender", "3D Animation"
                ]
            },
            "Media": {
                "Video": [
                    "Video Editing", "Short Video", "YouTube Video", "Reels/TikTok",
                    "Motion Graphics", "Subtitle Editing", "Video Color Correction"
                ],
                "Audio": [
                    "Audio Editing", "Podcast Editing", "Voice Over", "Sound Design"
                ],
                "Photography": [
                    "Photo Editing", "Product Photography", "Portrait Photography",
                    "Event Photography", "Background Removal"
                ]
            },
            "Marketing": {
                "Digital Marketing": [
                    "SMM", "Instagram Marketing", "TikTok Marketing", "Facebook Marketing",
                    "Google Ads", "Target Advertising", "Email Marketing"
                ],
                "SEO": [
                    "SEO Optimization", "Keyword Research", "Technical SEO",
                    "Local SEO", "SEO Content"
                ],
                "Content": [
                    "Copywriting", "Blog Writing", "Product Description",
                    "Technical Writing", "Translation", "Proofreading"
                ]
            },
            "Biznes": {
                "Business": [
                    "Business Plan", "Market Research", "Business Consulting",
                    "Financial Analysis", "Project Management"
                ],
                "Office": [
                    "Excel", "Word", "PowerPoint", "Data Entry",
                    "Virtual Assistant", "Document Formatting"
                ]
            },
            "Ta'lim": {
                "Fanlar": [
                    "Matematika", "Fizika", "Kimyo", "Biologiya", "Ingliz Tili",
                    "Ona Tili", "Tarix", "Informatika"
                ],
                "Dasturlash darslari": [
                    "Python Darsi", "JavaScript Darsi", "C++ Darsi",
                    "Web Dasturlash Darsi", "Scratch Darsi"
                ]
            },
            "Uy va xizmatlar": {
                "Uy ishlari": [
                    "Tozalash", "General Cleaning", "Uy yig'ishtirish",
                    "Ovqat pishirish", "Idish yuvish", "Kir yuvish"
                ],
                "Ta'mirlash": [
                    "Santexnik", "Elektrik", "Bo'yoqchi", "G'isht terish",
                    "Plitka", "Mebel ta'mirlash", "Konditsioner ta'miri"
                ],
                "Xizmatlar": [
                    "Yuk tashish", "Kuryer", "Haydovchi", "Bog'bon",
                    "Ko'chirish xizmati", "Mebel yig'ish"
                ]
            },
            "Go'zallik": {
                "Beauty": [
                    "Sartarosh", "Soch turmagi", "Manikyur", "Pedikyur",
                    "Makeup", "Qosh dizayni", "Kosmetolog"
                ]
            }
        }

        service_translations = {
          "Backend": "Backend",
          "Frontend": "Frontend",
          "Mobile": "Mobil ilovalar",
          "Desktop": "Kompyuter dasturlari",
          "Game Development": "O‘yin yaratish",
          "Automation": "Avtomatlashtirish",
          "Dizayn": "Dizayn",
          "Grafik": "Grafika",
          "Photography": "Fotosurat",
          "Digital Marketing": "Raqamli marketing",
          "Content": "Kontent",
          "Business": "Biznes xizmatlari",
          "Office": "Ofis",
          "Beauty": "Go‘zallik",
          "Python Backend": "Python backend",
          "API Integration": "API integratsiyasi",
          "Database Backend": "Ma’lumotlar bazasi backend",
          "Authentication": "Autentifikatsiya",
          "Payment Integration": "To‘lov integratsiyasi",
          "UI Development": "UI yaratish",
          "Responsive Web": "Moslashuvchan veb-sayt",
          "Landing Page": "Bir sahifali sayt",
          "Figma to HTML": "Figma dizaynini HTMLga o‘tkazish",
          "Frontend Bug Fix": "Frontend xatolarini tuzatish",
          "Mobile UI": "Mobil UI",
          "Mobile Bug Fix": "Mobil xatolarni tuzatish",
          "Desktop App": "Kompyuter dasturi",
          "C++ App": "C++ dasturi",
          "C# App": "C# dasturi",
          "Java App": "Java dasturi",
          "2D Game": "2D o‘yin",
          "3D Game": "3D o‘yin",
          "Game Bug Fix": "O‘yin xatolarini tuzatish",
          "Python Automation": "Python avtomatlashtirish",
          "Web Scraping": "Veb-ma’lumot yig‘ish",
          "Browser Automation": "Brauzerni avtomatlashtirish",
          "Data Processing": "Ma’lumotlarni qayta ishlash",
          "Excel Automation": "Excel avtomatlashtirish",
          "Bot Automation": "Botlarni avtomatlashtirish",
          "Website UI/UX": "Veb-sayt UI/UX",
          "Mobile UI/UX": "Mobil UI/UX",
          "Dashboard Design": "Boshqaruv paneli dizayni",
          "Prototype": "Prototip",
          "Design System": "Dizayn tizimi",
          "Logo Design": "Logotip dizayni",
          "Banner Design": "Banner dizayni",
          "Poster Design": "Poster dizayni",
          "Social Media Design": "Ijtimoiy tarmoq dizayni",
          "Presentation Design": "Taqdimot dizayni",
          "Business Card": "Vizitka dizayni",
          "Illustration": "Illustratsiya",
          "Infographic": "Infografika",
          "3D Modeling": "3D modellashtirish",
          "3D Product Design": "3D mahsulot dizayni",
          "Blender": "Blender",
          "3D Animation": "3D animatsiya",
          "Video Editing": "Video montaj",
          "Short Video": "Qisqa video",
          "YouTube Video": "YouTube video",
          "Reels/TikTok": "Reels/TikTok video",
          "Motion Graphics": "Harakatli grafika",
          "Subtitle Editing": "Subtitr tahriri",
          "Video Color Correction": "Video ranglarini to‘g‘rilash",
          "Audio Editing": "Audio tahriri",
          "Podcast Editing": "Podkast tahriri",
          "Voice Over": "Ovozli ijro",
          "Sound Design": "Ovoz dizayni",
          "Photo Editing": "Foto tahriri",
          "Product Photography": "Mahsulot fotosurati",
          "Portrait Photography": "Portret fotosurati",
          "Event Photography": "Tadbir fotosurati",
          "Background Removal": "Fon olib tashlash",
          "Instagram Marketing": "Instagram marketingi",
          "TikTok Marketing": "TikTok marketingi",
          "Facebook Marketing": "Facebook marketingi",
          "Google Ads": "Google reklamalari",
          "Target Advertising": "Maqsadli reklama",
          "Email Marketing": "Elektron pochta marketingi",
          "SEO Optimization": "SEO optimizatsiyasi",
          "Keyword Research": "Kalit so‘zlarni tadqiq qilish",
          "Technical SEO": "Texnik SEO",
          "Local SEO": "Mahalliy SEO",
          "SEO Content": "SEO kontenti",
          "Copywriting": "Kopirayting",
          "Blog Writing": "Blog yozish",
          "Product Description": "Mahsulot tavsifi",
          "Technical Writing": "Texnik yozuv",
          "Translation": "Tarjima",
          "Proofreading": "Tahrir va tekshiruv",
          "Business Plan": "Biznes reja",
          "Market Research": "Bozor tadqiqoti",
          "Business Consulting": "Biznes konsultatsiyasi",
          "Financial Analysis": "Moliyaviy tahlil",
          "Project Management": "Loyiha boshqaruvi",
          "Data Entry": "Ma’lumot kiritish",
          "Virtual Assistant": "Virtual yordamchi",
          "Document Formatting": "Hujjatlarni formatlash",
          "General Cleaning": "Umumiy tozalash",
          "Makeup": "Pardoz",
          "Foydalanuvchi": "Foydalanuvchi"
}

        for old_name, new_name in service_translations.items():
            if old_name != new_name:
                cursor.execute(
                    "UPDATE services SET name=? WHERE name=?",
                    (new_name, old_name)
                )

        def ensure_service(name, parent_id=None):
            cursor.execute(
                "SELECT id FROM services WHERE name=? AND parent_id IS ?",
                (name, parent_id)
            )
            found = cursor.fetchone()
            if found:
                return found[0]
            cursor.execute(
                "INSERT INTO services(name,parent_id,created_by) VALUES(?,?,NULL)",
                (name, parent_id)
            )
            return cursor.lastrowid

        for root_name, groups in catalog.items():
            translated_root = service_translations.get(root_name, root_name)
            root_id = ensure_service(translated_root)
            for group_name, leaves in groups.items():
                translated_group = service_translations.get(group_name, group_name)
                group_id = ensure_service(translated_group, root_id)
                for leaf_name in leaves:
                    translated_leaf = service_translations.get(leaf_name, leaf_name)
                    ensure_service(translated_leaf, group_id)

        conn.commit()
        conn.close()

    def q(self, sql, args=()):
        conn = self._query_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, args)
            first_keyword = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
            if first_keyword not in {"SELECT", "PRAGMA", "EXPLAIN"}:
                conn.commit()
            return QueryResult(conn, cursor)
        except Exception:
            conn.rollback()
            cursor.close()
            raise


class QueryResult:
    def __init__(self, conn, cursor):
        self.conn = conn
        self.cursor = cursor

    def fetchone(self):
        row = self.cursor.fetchone()
        self.close()
        return row

    def fetchall(self):
        rows = self.cursor.fetchall()
        self.close()
        return rows

    @property
    def rowcount(self):
        return self.cursor.rowcount

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    def close(self):
        if self.cursor is not None:
            self.cursor.close()
        self.cursor = None
        self.conn = None


db = DB()


# -------- JWT & AUTHORIZATION --------
def token(uid, role="user", token_version=0):
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {
            "id": int(uid),
            "role": role,
            "ver": int(token_version),
            "iat": now,
            "exp": now + datetime.timedelta(hours=app.config["JWT_TTL_HOURS"]),
            "iss": "finjob",
            "aud": "finjob-client",
        },
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )


def auth(f):
    @wraps(f)
    def w(*a, **k):
        t = request.headers.get("Authorization", "")
        parts = t.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify({"msg": "Kirish tokeni talab qilinadi"}), 401
        try:
            d = jwt.decode(
                parts[1],
                app.config["SECRET_KEY"],
                algorithms=["HS256"],
                issuer="finjob",
                audience="finjob-client",
            )
            uid = int(d["id"])
            user = db.q("SELECT role, COALESCE(token_version,0), COALESCE(is_blocked,0) FROM users WHERE id=?", (uid,)).fetchone()
            if not user:
                return jsonify({"msg": "Kirish tokeni yaroqsiz"}), 401
            if int(d.get("ver", -1)) != int(user[1] or 0):
                return jsonify({"msg": "Sessiya muddati tugagan. Qayta kiring."}), 401
            request.uid = uid
            request.user_role = user[0] or "user"
            if request.user_role != "admin" and _active_block_row(request.uid, "full"):
                full_allowed = (
                    request.path == "/appeals"
                    or request.path == "/notifications"
                    or request.path == "/notifications/read"
                    or (request.path == "/profile" and request.method == "GET")
                    or request.path == "/logout"
                )
                if not full_allowed:
                    block = _active_block_row(request.uid, "full")
                    return jsonify({
                        "msg": f"To‘liq blok mavjud. Sabab: {block[3]}.",
                        "blocked": True,
                        "block_type": "full",
                        "block_id": block[0],
                        "reason": block[3],
                        "expires_at": block[6],
                    }), 403
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError, TypeError, ValueError):
            return jsonify({"msg": "Kirish tokeni yaroqsiz yoki muddati tugagan"}), 401
        return f(*a, **k)

    return w


def admin_required(f):
    @wraps(f)
    @auth
    def w(*a, **k):
        u = db.q("SELECT role FROM users WHERE id=?", (request.uid,)).fetchone()
        role = u[0] if u else "user"
        if role != "admin":
            return jsonify({"msg": "Ruxsat berilmadi: bu amal faqat administratorlar uchun."}), 403
        return f(*a, **k)

    return w


def rows(r, cols):
    return [dict(zip(cols, i)) for i in r]


def admin_audit(action, target_type="", target_id=None, details=""):
    try:
        db.q(
            """INSERT INTO admin_audit_log(admin_id,action,target_type,target_id,details,created_at)
               VALUES(?,?,?,?,?,?)""",
            (
                int(getattr(request, "uid", 0) or 0),
                str(action)[:120],
                str(target_type)[:40],
                target_id,
                str(details)[:2000],
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ),
        ).close()
    except Exception:
        app.logger.exception("Admin audit log yozilmadi")


BLOCK_TYPE_LABELS = {
    "full": "To‘liq blok",
    "chat": "Chat blok",
    "job_creation": "Ish yaratish blok",
    "job_accept": "Ish qabul qilish blok",
    "proposal": "Taklif yuborish blok",
    "rating": "Baholash blok",
    "withdrawal": "Mablag‘ yechish blok",
}


def _active_block_row(user_id, block_type=None):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if block_type:
        return db.q(
            """SELECT id,user_id,block_type,reason,duration_minutes,created_at,expires_at,active,created_by,lifted_at,lifted_by
               FROM user_blocks
               WHERE user_id=? AND active=1 AND block_type=?
                 AND (expires_at IS NULL OR expires_at>?)
               ORDER BY id DESC LIMIT 1""",
            (user_id, block_type, now),
        ).fetchone()
    return db.q(
        """SELECT id,user_id,block_type,reason,duration_minutes,created_at,expires_at,active,created_by,lifted_at,lifted_by
           FROM user_blocks
           WHERE user_id=? AND active=1
             AND (expires_at IS NULL OR expires_at>?)
           ORDER BY id DESC""",
        (user_id, now),
    ).fetchall()


def _block_payload(row):
    if not row:
        return None
    return {
        "id": row[0], "user_id": row[1], "block_type": row[2],
        "block_label": BLOCK_TYPE_LABELS.get(row[2], row[2]),
        "reason": row[3], "duration_minutes": row[4],
        "created_at": row[5], "expires_at": row[6], "active": bool(row[7]),
        "created_by": row[8], "lifted_at": row[9], "lifted_by": row[10],
    }


def enforce_block(block_type):
    if getattr(request, "user_role", "user") == "admin":
        return None
    block = _active_block_row(request.uid, "full") or _active_block_row(request.uid, block_type)
    if not block:
        return None
    expiry = "muddatsiz" if not block[6] else block[6]
    return jsonify({
        "msg": f"{BLOCK_TYPE_LABELS.get(block[2], block[2])} mavjud. Sabab: {block[3]}. Tugash vaqti: {expiry}.",
        "blocked": True,
        "block_type": block[2],
        "block_id": block[0],
        "reason": block[3],
        "expires_at": block[6],
    }), 403


def _ensure_user_blocked(user_id, block_type):
    return _active_block_row(user_id, "full") or _active_block_row(user_id, block_type)


def create_notification(user_id, notification_type, title, message, link=""):
    if not user_id:
        return
    now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.q(
        "INSERT INTO notifications(user_id,type,title,message,link,created_at) VALUES(?,?,?,?,?,?)",
        (user_id, notification_type, title, message, link, now_time),
    ).close()


def notify_matching_users(job_id, job_title, creator_id):
    service_rows = db.q(
        """SELECT DISTINCT s.name
           FROM job_services js
           JOIN services s ON s.id = js.service_id
           WHERE js.job_id=? AND s.name IS NOT NULL AND TRIM(s.name)!=''""",
        (job_id,),
    ).fetchall()
    service_names = [str(row[0]).strip() for row in service_rows if row[0]]
    job = db.q("SELECT custom_service FROM jobs WHERE id=?", (job_id,)).fetchone()
    if job and job[0]:
        service_names.extend([item.strip() for item in str(job[0]).split(",") if item.strip()])
    if not service_names:
        return
    normalized_services = [item.casefold() for item in service_names]
    users = db.q("SELECT id, skills FROM users WHERE id!=? AND skills IS NOT NULL AND TRIM(skills)!=''", (creator_id,)).fetchall()
    for user_id, skills in users:
        user_skills = [item.strip().casefold() for item in str(skills).replace(";", ",").replace("\\n", ",").split(",") if item.strip()]
        matched = any(
            skill == service or (len(skill) >= 3 and len(service) >= 3 and (skill in service or service in skill))
            for skill in user_skills for service in normalized_services
        )
        if matched:
            create_notification(user_id, "matching_job", "Sizga mos yangi ish", f"Sizning sohalaringizga mos yangi ish yaratildi: {job_title}", "/jobs")


def _verification_payload(user_id):
    row = db.q(
        """SELECT email_verified, phone_verified, identity_verified, auth_provider, verification_updated_at
           FROM users WHERE id=?""",
        (user_id,),
    ).fetchone()
    if not row:
        return {
            "email_verified": False,
            "phone_verified": False,
            "identity_verified": False,
            "badges": [],
            "updated_at": "",
        }
    email_verified = bool(row[0])
    phone_verified = bool(row[1])
    identity_verified = bool(row[2])
    badges = []
    if email_verified:
        badges.append({"key": "email_verified", "label": "Email tasdiqlangan", "description": "Elektron pochta manzili tasdiqlangan."})
    if phone_verified:
        badges.append({"key": "phone_verified", "label": "Telefon tasdiqlangan", "description": "Telefon raqami administrator tomonidan tasdiqlangan."})
    if identity_verified:
        badges.append({"key": "identity_verified", "label": "Shaxs tasdiqlangan", "description": "Shaxsni tasdiqlash jarayoni administrator tomonidan yakunlangan."})
    return {
        "email_verified": email_verified,
        "phone_verified": phone_verified,
        "identity_verified": identity_verified,
        "badges": badges,
        "updated_at": row[4] or "",
    }


def _reputation_payload(user_id):
    rating = db.q(
        "SELECT AVG(score), COUNT(*) FROM ratings WHERE to_user=?",
        (user_id,),
    ).fetchone()
    average_rating = round(float(rating[0]), 1) if rating and rating[0] is not None else 0.0
    reviews_count = int(rating[1] or 0) if rating else 0
    worker_jobs = int(db.q("SELECT COUNT(*) FROM jobs WHERE worker_id=?", (user_id,)).fetchone()[0] or 0)
    completed_worker_jobs = int(db.q(
        "SELECT COUNT(*) FROM jobs WHERE worker_id=? AND status='finished'", (user_id,)
    ).fetchone()[0] or 0)
    client_jobs = int(db.q("SELECT COUNT(*) FROM jobs WHERE user_id=?", (user_id,)).fetchone()[0] or 0)
    completed_client_jobs = int(db.q(
        "SELECT COUNT(*) FROM jobs WHERE user_id=? AND status='finished'", (user_id,)
    ).fetchone()[0] or 0)
    success_rate = round((completed_worker_jobs / worker_jobs) * 100, 1) if worker_jobs else 0.0
    badges = []
    if completed_worker_jobs >= 20:
        badges.append({"key": "experienced", "label": "Tajribali", "description": "20 yoki undan ko‘p ishni muvaffaqiyatli yakunlagan."})
    if completed_worker_jobs >= 10 and success_rate >= 90:
        badges.append({"key": "top_provider", "label": "Top Provider", "description": "Kamida 10 ta ish va 90% yoki undan yuqori success rate."})
    if reviews_count >= 5 and average_rating >= 4.5:
        badges.append({"key": "trusted", "label": "Ishonchli", "description": "Kamida 5 ta sharh va 4.5+ o‘rtacha reyting."})
    return {
        "average_rating": average_rating,
        "reviews_count": reviews_count,
        "worker_jobs": worker_jobs,
        "completed_worker_jobs": completed_worker_jobs,
        "client_jobs": client_jobs,
        "completed_client_jobs": completed_client_jobs,
        "success_rate": success_rate,
        "badges": badges,
    }


@app.route("/verification", methods=["GET"])
@auth
def get_verification():
    return jsonify(_verification_payload(request.uid))


@app.route("/admin/user/<int:user_id>/verification", methods=["PATCH"])
@admin_required
def update_user_verification(user_id):
    data = request.json or {}
    target = db.q("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
    if not target:
        return jsonify({"msg": "Foydalanuvchi topilmadi"}), 404
    allowed = {"email_verified", "phone_verified", "identity_verified"}
    updates = {key: bool(data[key]) for key in allowed if key in data}
    if not updates:
        return jsonify({"msg": "Tasdiqlash maydoni kiritilmagan"}), 400
    assignments = ", ".join(f"{key}=?" for key in updates)
    values = [int(value) for value in updates.values()]
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    values.extend([now, user_id])
    db.q(
        f"UPDATE users SET {assignments}, verification_updated_at=? WHERE id=?",
        tuple(values),
    ).close()
    admin_audit("verification_update", "user", user_id, json.dumps(updates, ensure_ascii=False))
    return jsonify({"msg": "Tasdiqlash holati yangilandi", **_verification_payload(user_id)})


@app.route("/reputation", methods=["GET"])
@auth
def get_my_reputation():
    return jsonify(_reputation_payload(request.uid))


@app.route("/disputes/eligible-jobs", methods=["GET"])
@auth
def eligible_dispute_jobs():
    requested_job_id = request.args.get("job_id", "").strip()
    if requested_job_id and not requested_job_id.isdigit():
        return jsonify({"msg": "Ish identifikatori noto‘g‘ri", "items": []}), 400

    query = """SELECT j.id,j.title,j.status,j.user_id,j.worker_id
               FROM jobs j
               WHERE j.worker_id IS NOT NULL
                 AND (j.user_id=? OR j.worker_id=?)
                 AND j.status IN ('payment_pending','accepted','pending_finish','finished')
                 AND NOT EXISTS (
                     SELECT 1 FROM disputes d
                     WHERE d.job_id=j.id AND d.status IN ('open','reviewing')
                 )"""
    params = [request.uid, request.uid]
    if requested_job_id:
        query += " AND j.id=?"
        params.append(int(requested_job_id))
    query += " ORDER BY j.id DESC"
    if not requested_job_id:
        query += " LIMIT 200"

    rows = db.q(query, tuple(params)).fetchall()
    return jsonify({"items": [{
        "id": row[0], "title": row[1], "status": row[2],
        "user_id": row[3], "worker_id": row[4],
    } for row in rows]})


@app.route("/disputes", methods=["GET", "POST"])
@auth
def disputes():
    if request.method == "GET":
        rows_data = db.q(
            """SELECT d.id,d.job_id,d.opened_by,d.against_user_id,d.category,d.description,d.evidence,
                      d.status,d.admin_response,d.created_at,d.updated_at,d.resolved_at,
                      j.title,j.status,ou.username,au.username
               FROM disputes d
               JOIN jobs j ON j.id=d.job_id
               LEFT JOIN users ou ON ou.id=d.opened_by
               LEFT JOIN users au ON au.id=d.against_user_id
               WHERE (d.opened_by=? OR d.against_user_id=?)
                 AND d.status IN ('open','reviewing')
               ORDER BY d.id DESC LIMIT 100""",
            (request.uid, request.uid),
        ).fetchall()
        return jsonify([{
            "id": row[0], "job_id": row[1], "opened_by": row[2], "against_user_id": row[3],
            "category": row[4], "description": row[5], "evidence": row[6] or "",
            "status": row[7], "admin_response": row[8] or "", "created_at": row[9],
            "updated_at": row[10], "resolved_at": row[11], "job_title": row[12] or "",
            "job_status": row[13] or "", "opened_by_username": row[14] or "",
            "against_username": row[15] or "",
        } for row in rows_data])

    data = request.json or {}
    try:
        job_id = int(data.get("job_id"))
    except (TypeError, ValueError):
        return jsonify({"msg": "Ish identifikatori noto‘g‘ri"}), 400
    category = str(data.get("category", "")).strip()
    description = str(data.get("description", "")).strip()
    evidence = str(data.get("evidence", "")).strip()
    if category not in {"payment", "quality", "deadline", "communication", "other"}:
        return jsonify({"msg": "Nizo kategoriyasi noto‘g‘ri"}), 400
    if not description or len(description) > 3000:
        return jsonify({"msg": "Nizo tavsifi 1–3000 belgidan iborat bo‘lishi kerak"}), 400
    if len(evidence) > 3000:
        return jsonify({"msg": "Dalillar 3000 belgidan oshmasligi kerak"}), 400

    job = db.q("SELECT user_id,worker_id,status,title FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi"}), 404
    owner_id, worker_id, job_status, job_title = job
    if not worker_id or request.uid not in (owner_id, worker_id):
        return jsonify({"msg": "Faqat ish ishtirokchilari nizo ochishi mumkin"}), 403
    if job_status not in ("payment_pending", "accepted", "pending_finish", "finished"):
        return jsonify({"msg": "Bu ish holatida nizo ochish mumkin emas"}), 400
    existing = db.q(
        "SELECT id FROM disputes WHERE job_id=? AND status IN ('open','reviewing')",
        (job_id,),
    ).fetchone()
    if existing:
        return jsonify({"msg": "Bu ish bo‘yicha allaqachon ochiq nizo mavjud", "dispute_id": existing[0]}), 409

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    against_user = worker_id if request.uid == owner_id else owner_id
    result = db.q(
        """INSERT INTO disputes(job_id,opened_by,against_user_id,category,description,evidence,status,created_at,updated_at)
           VALUES(?,?,?,?,?,?, 'open', ?, ?)""",
        (job_id, request.uid, against_user, category, description, evidence, now, now),
    )
    dispute_id = result.lastrowid
    result.close()
    for admin in db.q("SELECT id FROM users WHERE role='admin'").fetchall():
        create_notification(
            admin[0],
            "dispute",
            "Yangi nizo",
            f"{job_title}: yangi nizo ochildi.",
            "/disputes",
        )
    return jsonify({"msg": "Nizo muvaffaqiyatli ochildi", "id": dispute_id}), 201


@app.route("/admin/disputes")
@admin_required
def admin_disputes():
    rows_data = db.q(
        """SELECT d.id,d.job_id,d.opened_by,d.against_user_id,d.category,d.description,d.evidence,
                  d.status,d.admin_response,d.created_at,d.updated_at,d.resolved_at,
                  j.title,ou.username,au.username,d.decision,d.decision_for_user_id,
                  d.payment_action,d.job_action,d.sanction_user_id,d.sanction_type,d.sanction_duration_minutes
           FROM disputes d
           JOIN jobs j ON j.id=d.job_id
           LEFT JOIN users ou ON ou.id=d.opened_by
           LEFT JOIN users au ON au.id=d.against_user_id
           ORDER BY CASE d.status WHEN 'open' THEN 0 WHEN 'reviewing' THEN 1 ELSE 2 END, d.id DESC
           LIMIT 200"""
    ).fetchall()
    return jsonify([{
        "id": r[0], "job_id": r[1], "opened_by": r[2], "against_user_id": r[3],
        "category": r[4], "description": r[5], "evidence": r[6] or "",
        "status": r[7], "admin_response": r[8] or "", "created_at": r[9],
        "updated_at": r[10], "resolved_at": r[11], "job_title": r[12] or "",
        "opened_by_username": r[13] or "", "against_username": r[14] or "",
        "decision": r[15] or "", "decision_for_user_id": r[16],
        "payment_action": r[17] or "none", "job_action": r[18] or "none",
        "sanction_user_id": r[19], "sanction_type": r[20] or "none",
        "sanction_duration_minutes": r[21],
    } for r in rows_data])


@app.route("/admin/disputes/<int:dispute_id>", methods=["PATCH"])
@admin_required
def update_dispute(dispute_id):
    data = request.json or {}
    status = str(data.get("status", "")).strip()
    response = str(data.get("admin_response", "")).strip()
    decision = str(data.get("decision", "")).strip().lower()
    payment_action = str(data.get("payment_action", "none")).strip().lower()
    job_action = str(data.get("job_action", "none")).strip().lower()
    sanction_type = str(data.get("sanction_type", "none")).strip().lower()
    sanction_target = str(data.get("sanction_target", "opponent")).strip().lower()
    duration_raw = data.get("sanction_duration_minutes", "1440")

    decisions = {
        "favor_opener": "Nizo ochgan tomon foydasiga",
        "favor_opponent": "Qarshi tomon foydasiga",
        "mutual_agreement": "Tomonlar kelishuvi bilan",
        "insufficient_evidence": "Dalillar yetarli emas",
        "policy_violation": "Qoidabuzarlik aniqlandi",
        "no_violation": "Qoidabuzarlik aniqlanmadi",
    }
    if status not in {"open", "reviewing", "resolved", "rejected"}:
        return jsonify({"msg": "Nizo holati noto‘g‘ri"}), 400
    if decision and decision not in decisions:
        return jsonify({"msg": "Hukm turi noto‘g‘ri"}), 400
    if payment_action not in {"none", "refund_payer", "release_to_worker"}:
        return jsonify({"msg": "To‘lov chorasi noto‘g‘ri"}), 400
    if job_action not in {"none", "block"}:
        return jsonify({"msg": "Ish bo‘yicha chora noto‘g‘ri"}), 400
    if sanction_type not in {"none", *BLOCK_TYPE_LABELS.keys()}:
        return jsonify({"msg": "Foydalanuvchi uchun chora noto‘g‘ri"}), 400
    if len(response) > 3000:
        return jsonify({"msg": "Admin javobi juda uzun"}), 400

    is_final = status in {"resolved", "rejected"}
    if not is_final and (payment_action != "none" or job_action != "none" or sanction_type != "none"):
        return jsonify({"msg": "Pul, ish yoki akkaunt bo‘yicha choralar faqat yakuniy hukmda qo‘llanadi"}), 400
    if payment_action == "release_to_worker" and job_action == "block":
        return jsonify({"msg": "Ishni bloklash va to‘lovni ijrochiga o‘tkazishni bir hukmda tanlab bo‘lmaydi"}), 400
    if sanction_type != "none" and sanction_target not in {"opener", "opponent"}:
        return jsonify({"msg": "Cheklov qo‘yiladigan tomon noto‘g‘ri"}), 400

    dispute = db.q(
        """SELECT opened_by,against_user_id,job_id,status,sanction_user_id,sanction_type
           FROM disputes WHERE id=?""",
        (dispute_id,),
    ).fetchone()
    if not dispute:
        return jsonify({"msg": "Nizo topilmadi"}), 404

    opener_id, opponent_id, job_id, old_status, previous_sanction_user_id, previous_sanction_type = dispute
    decision_for_user_id = (
        opener_id if decision == "favor_opener" else
        opponent_id if decision == "favor_opponent" else None
    )

    sanction_user_id = None
    sanction_duration = None
    prior_sanction_exists = False
    if sanction_type != "none":
        sanction_user_id = opener_id if sanction_target == "opener" else opponent_id
        if sanction_user_id == int(request.uid):
            return jsonify({"msg": "O‘zingizga cheklov qo‘ya olmaysiz"}), 400
        target = db.q("SELECT role FROM users WHERE id=?", (sanction_user_id,)).fetchone()
        if not target:
            return jsonify({"msg": "Cheklov qo‘yiladigan foydalanuvchi topilmadi"}), 404
        if target[0] == "admin":
            return jsonify({"msg": "Administrator hisobini nizo orqali bloklab bo‘lmaydi"}), 400
        if duration_raw not in (None, "", "null", "0", 0):
            try:
                sanction_duration = int(duration_raw)
            except (TypeError, ValueError):
                return jsonify({"msg": "Cheklov muddati noto‘g‘ri"}), 400
            if sanction_duration < 1 or sanction_duration > 525600:
                return jsonify({"msg": "Cheklov muddati 1 daqiqadan 365 kungacha bo‘lishi kerak"}), 400

        existing_block = _active_block_row(sanction_user_id, sanction_type)
        if existing_block:
            prior_sanction_exists = (
                previous_sanction_user_id == sanction_user_id and
                previous_sanction_type == sanction_type
            )
            if not prior_sanction_exists:
                return jsonify({"msg": "Bu foydalanuvchida ushbu turdagi faol cheklov allaqachon mavjud"}), 409

    # Apply a requested escrow decision first, so a failed payment action never records a false ruling.
    if payment_action != "none":
        payment_handler = (
            app.config.get("FINJOB_REFUND_PAYMENT") if payment_action == "refund_payer"
            else app.config.get("FINJOB_RELEASE_PAYMENT")
        )
        if not payment_handler:
            return jsonify({"msg": "To‘lov amali hozir mavjud emas"}), 503
        payment_ok, payment_message, payment_data = payment_handler(job_id)
        if not payment_ok:
            return jsonify({"msg": payment_message or "To‘lov bo‘yicha chora bajarilmadi"}), 400

    if job_action == "block":
        db.q(
            "UPDATE jobs SET status='blocked', finished_at=NULL, owner_finished=0, worker_finished=0 WHERE id=?",
            (job_id,),
        ).close()

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    expires_at = None
    if sanction_type != "none" and sanction_user_id and not prior_sanction_exists:
        expires_at = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=sanction_duration)
        ).isoformat() if sanction_duration else None
        block_result = db.q(
            """INSERT INTO user_blocks(user_id,block_type,reason,duration_minutes,created_at,expires_at,active,created_by)
               VALUES(?,?,?,?,?,?,1,?)""",
            (sanction_user_id, sanction_type, f"Nizo #{dispute_id}: {response}"[:2000],
             sanction_duration, now, expires_at, request.uid),
        )
        block_id = block_result.lastrowid
        block_result.close()
        if sanction_type == "full":
            db.q("UPDATE users SET is_blocked=1 WHERE id=?", (sanction_user_id,)).close()
        deadline = "muddatsiz" if not expires_at else expires_at
        create_notification(
            sanction_user_id, "account_moderation", "Hisobingizga cheklov qo‘yildi",
            f"Nizo #{dispute_id} bo‘yicha {BLOCK_TYPE_LABELS[sanction_type]} qo‘yildi. Sabab: {response}. Muddati: {deadline}.",
            "/appeals",
        )

    db.q(
        """UPDATE disputes SET status=?,admin_response=?,updated_at=?,resolved_at=?,resolved_by=?,
                  decision=?,decision_for_user_id=?,payment_action=?,job_action=?,
                  sanction_user_id=?,sanction_type=?,sanction_duration_minutes=?
           WHERE id=?""",
        (
            status, response, now, now if is_final else None, request.uid if is_final else None,
            decision, decision_for_user_id, payment_action, job_action,
            sanction_user_id, sanction_type, sanction_duration, dispute_id,
        ),
    ).close()

    if is_final:
        title = "Nizo bo‘yicha yakuniy qaror"
        parts = []
        if decision:
            parts.append(f"Hukm: {decisions[decision]}.")
        if response:
            parts.append(response)
        if payment_action == "refund_payer":
            parts.append("To‘lov buyurtmachiga qaytarildi.")
        elif payment_action == "release_to_worker":
            parts.append("To‘lov ijrochiga o‘tkazildi.")
        if job_action == "block":
            parts.append("Ish bloklandi.")
        if sanction_type != "none":
            parts.append(f"{BLOCK_TYPE_LABELS[sanction_type]} qo‘llandi.")
        notice_message = " ".join(parts) or "Administrator nizo bo‘yicha qaror chiqardi."
        for uid in {opener_id, opponent_id}:
            create_notification(uid, "dispute_update", title, notice_message, "/disputes")

    audit_parts = [f"status={status}", f"decision={decision or 'not_set'}",
                   f"payment={payment_action}", f"job={job_action}"]
    if sanction_type != "none":
        audit_parts.append(f"sanction={sanction_type}; target={sanction_user_id}; minutes={sanction_duration}")
    admin_audit("dispute_decision", "dispute", dispute_id, "; ".join(audit_parts))
    return jsonify({
        "msg": "Nizo bo‘yicha hukm va tanlangan choralar saqlandi.",
        "status": status, "decision": decision, "payment_action": payment_action,
        "job_action": job_action, "sanction_type": sanction_type,
        "sanction_user_id": sanction_user_id,
    })

register_payment_routes(app, db, auth, admin_required, create_notification, admin_audit, enforce_block)

@app.route("/notifications")
@auth
def get_notifications():
    items = db.q(
        """SELECT id,type,title,message,link,is_read,created_at
           FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50""",
        (request.uid,),
    ).fetchall()
    unread = db.q("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (request.uid,)).fetchone()[0]
    return jsonify({"items":[dict(zip(["id","type","title","message","link","is_read","created_at"], item)) for item in items],"unread":unread})


@app.route("/notifications/read", methods=["POST"])
@auth
def read_notifications():
    db.q("UPDATE notifications SET is_read=1 WHERE user_id=?", (request.uid,)).close()
    return jsonify({"msg":"ok"})


@app.route("/report", methods=["POST"])
@auth
def create_report():
    d=request.json or {}
    reason=str(d.get("reason","")).strip()
    details=str(d.get("details","")).strip()
    try:
        job_id=int(d["job_id"]) if d.get("job_id") else None
        reported_user_id=int(d["reported_user_id"]) if d.get("reported_user_id") else None
        message_id=int(d["message_id"]) if d.get("message_id") else None
    except (TypeError,ValueError):
        return jsonify({"msg":"Identifikator noto‘g‘ri"}),400
    if not reason or len(reason)>120:
        return jsonify({"msg":"Shikoyat sababini kiriting"}),400
    if len(details)>2000:
        return jsonify({"msg":"Izoh 2000 belgidan oshmasligi kerak"}),400
    if reported_user_id == request.uid:
        return jsonify({"msg":"O‘zingiz ustingizdan shikoyat qila olmaysiz"}),400

    if message_id:
        message = db.q(
            """SELECT m.sender_id,m.receiver_id,m.job_id
               FROM messages m
               JOIN jobs j ON j.id=m.job_id
               WHERE m.id=? AND j.id=? AND (j.user_id=? OR j.worker_id=?)
               LIMIT 1""",
            (message_id, job_id, request.uid, request.uid),
        ).fetchone()
        if not message:
            return jsonify({"msg":"Bu xabar topilmadi yoki unga ruxsatingiz yo‘q"}),404
        sender_id, receiver_id, message_job_id = message
        if request.uid not in (sender_id, receiver_id):
            return jsonify({"msg":"Faqat chat ishtirokchilari xabarni shikoyat qila oladi"}),403
        target_user_id = sender_id if request.uid == receiver_id else receiver_id
        if reported_user_id != target_user_id:
            return jsonify({"msg":"Faqat shu xabarni yuborgan foydalanuvchi haqida shikoyat qilish mumkin"}),403
        job_status = db.q("SELECT status FROM jobs WHERE id=?", (message_job_id,)).fetchone()
        if not job_status:
            return jsonify({"msg":"Ish topilmadi"}),404
        now_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.q(
            "INSERT INTO reports(reporter_id,reported_user_id,job_id,message_id,reason,details,created_at) VALUES(?,?,?,?,?,?,?)",
            (request.uid,reported_user_id,message_job_id,message_id,reason,details,now_time)
        ).close()
    else:
        if not job_id or not reported_user_id:
            return jsonify({"msg":"Ish va shikoyat qilinadigan foydalanuvchini ko‘rsating"}),400
        job = db.q(
            "SELECT user_id, worker_id, status FROM jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if not job:
            return jsonify({"msg":"Ish topilmadi"}),404
        owner_id, worker_id, job_status = job
        if not worker_id or request.uid not in (owner_id, worker_id):
            return jsonify({"msg":"Faqat ish egasi yoki ishchi bir-biridan shikoyat qila oladi"}),403
        if job_status not in ("active", "payment_pending", "accepted", "pending_finish", "finished", "blocked"):
            return jsonify({"msg":"Bu ish bo‘yicha shikoyat qilish mumkin emas"}),400
        target_user_id = worker_id if request.uid == owner_id else owner_id
        if reported_user_id != target_user_id:
            return jsonify({"msg":"Faqat shu ishdagi boshqa ishtirokchi haqida shikoyat qilish mumkin"}),403
        now_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.q(
            "INSERT INTO reports(reporter_id,reported_user_id,job_id,message_id,reason,details,created_at) VALUES(?,?,?,?,?,?,?)",
            (request.uid,reported_user_id,job_id,None,reason,details,now_time)
        ).close()

    for admin in db.q("SELECT id FROM users WHERE role='admin'").fetchall():
        create_notification(admin[0],"report","Yangi shikoyat",reason,"/admin")
    return jsonify({"msg":"Shikoyatingiz qabul qilindi."}),201


@app.route("/admin/report/<int:report_id>", methods=["PATCH"])
@admin_required
def update_report(report_id):
    data = request.json or {}
    status = str(data.get("status", "")).strip().lower()
    response = str(data.get("admin_response", "")).strip()
    decision = str(data.get("decision", "")).strip().lower()
    payment_action = str(data.get("payment_action", "none")).strip().lower()
    job_action = str(data.get("job_action", "none")).strip().lower()
    notify_target = str(data.get("notify_target", "none")).strip().lower()
    sanction_target = str(data.get("sanction_target", "reported")).strip().lower()
    sanction_type = str(data.get("sanction_type", "none")).strip().lower()
    duration_raw = data.get("sanction_duration_minutes", 1440)
    rich_review = any(key in data for key in (
        "admin_response", "decision", "payment_action", "job_action",
        "notify_target", "sanction_target", "sanction_type", "sanction_duration_minutes"
    ))

    if status not in ("open", "reviewing", "resolved", "rejected"):
        return jsonify({"msg": "Shikoyat holati noto‘g‘ri"}), 400

    report = db.q(
        "SELECT reporter_id,reported_user_id,job_id,message_id,status FROM reports WHERE id=?",
        (report_id,)
    ).fetchone()
    if not report:
        return jsonify({"msg": "Shikoyat topilmadi"}), 404

    reporter_id, reported_user_id, job_id, message_id, old_status = report
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Legacy clients that only send status keep the former reviewed/refund/block behavior.
    if not rich_review:
        result = db.q("UPDATE reports SET status=? WHERE id=?", (status, report_id))
        if result.rowcount != 1:
            result.close()
            return jsonify({"msg": "Shikoyat topilmadi"}), 404
        result.close()
        if status in ("resolved", "rejected") and old_status != status:
            if status == "resolved":
                if job_id and not message_id:
                    refund_payment = app.config.get("FINJOB_REFUND_PAYMENT")
                    if refund_payment:
                        refund_ok, refund_message, _ = refund_payment(job_id)
                        if not refund_ok and refund_message not in ("Faqat waiting holatidagi to‘lovni refund qilish mumkin",):
                            db.q("UPDATE reports SET status=? WHERE id=?", (old_status, report_id)).close()
                            return jsonify({"msg": refund_message}), 400
                    db.q(
                        "UPDATE jobs SET status='blocked', finished_at=NULL, owner_finished=0, worker_finished=0 WHERE id=?",
                        (job_id,)
                    ).close()
            title = "Shikoyat hal qilindi" if status == "resolved" else "Shikoyat rad etildi"
            message = (
                "Administrator shikoyatni ko‘rib chiqdi. Ish bo‘yicha chora ko‘rildi."
                if status == "resolved" else "Administrator shikoyatni ko‘rib chiqdi va rad etdi."
            )
            for uid in {reporter_id, reported_user_id} - {None}:
                create_notification(uid, "report_update", title, message, "/jobs")
        admin_audit("report_status_update", "report", report_id, f"status={status}; legacy")
        return jsonify({"msg": "Shikoyat holati yangilandi", "status": status})

    decisions = {
        "violation", "no_violation", "insufficient_evidence", "duplicate", "mistake", "other"
    }
    if decision and decision not in decisions:
        return jsonify({"msg": "Shikoyat hukmi noto‘g‘ri"}), 400
    if payment_action not in {"none", "refund_payer", "release_to_worker"}:
        return jsonify({"msg": "To‘lov chorasi noto‘g‘ri"}), 400
    if job_action not in {"none", "block"}:
        return jsonify({"msg": "Ish chorasi noto‘g‘ri"}), 400
    if notify_target not in {"none", "reporter", "reported", "both"}:
        return jsonify({"msg": "Ogohlantirish oluvchisi noto‘g‘ri"}), 400
    if sanction_type not in {"none", *BLOCK_TYPE_LABELS.keys()}:
        return jsonify({"msg": "Foydalanuvchi chorasi noto‘g‘ri"}), 400
    if len(response) > 3000:
        return jsonify({"msg": "Admin izohi 3000 belgidan oshmasligi kerak"}), 400

    is_final = status in ("resolved", "rejected")
    has_actions = payment_action != "none" or job_action != "none" or sanction_type != "none" or notify_target != "none"
    if is_final and (not decision or not response):
        return jsonify({"msg": "Yakuniy shikoyat qarori uchun hukm va asoslangan admin izohi majburiy"}), 400
    if not is_final and has_actions:
        return jsonify({"msg": "Shikoyat choralarini yakuniy qaror bilan birga qo‘llang"}), 400
    if job_action == "block" and not job_id:
        return jsonify({"msg": "Bu shikoyatga bog‘langan ish yo‘q"}), 400
    if job_action == "block" and payment_action == "release_to_worker":
        return jsonify({"msg": "Ishni bloklash va pulni ijrochiga o‘tkazish bir vaqtda mumkin emas"}), 400
    if payment_action != "none" and (not job_id or message_id):
        return jsonify({"msg": "To‘lov amali faqat ish bo‘yicha shikoyatlarda mumkin"}), 400
    if notify_target in {"reporter", "both"} and not reporter_id:
        return jsonify({"msg": "Shikoyat yuboruvchisi topilmadi"}), 404
    if notify_target in {"reported", "both"} and not reported_user_id:
        return jsonify({"msg": "Shikoyat qilingan foydalanuvchi topilmadi"}), 404
    if sanction_type != "none" and sanction_target not in {"reporter", "reported"}:
        return jsonify({"msg": "Cheklov oluvchisi noto‘g‘ri"}), 400

    sanction_user_id = None
    sanction_duration = None
    existing_sanction = None
    if sanction_type != "none":
        sanction_user_id = reporter_id if sanction_target == "reporter" else reported_user_id
        if not sanction_user_id:
            return jsonify({"msg": "Cheklov oluvchisi topilmadi"}), 404
        if int(sanction_user_id) == int(request.uid):
            return jsonify({"msg": "O‘zingizga cheklov qo‘ya olmaysiz"}), 400
        target = db.q("SELECT role FROM users WHERE id=?", (sanction_user_id,)).fetchone()
        if not target:
            return jsonify({"msg": "Cheklov oluvchisi topilmadi"}), 404
        if target[0] == "admin":
            return jsonify({"msg": "Administrator hisobiga cheklov qo‘yib bo‘lmaydi"}), 400
        if duration_raw not in (None, "", "null", "0", 0):
            try:
                sanction_duration = int(duration_raw)
            except (TypeError, ValueError):
                return jsonify({"msg": "Cheklov muddati noto‘g‘ri"}), 400
            if sanction_duration < 1 or sanction_duration > 525600:
                return jsonify({"msg": "Cheklov muddati 1 daqiqadan 365 kungacha bo‘lishi kerak"}), 400
        existing_sanction = _active_block_row(sanction_user_id, sanction_type)
        if existing_sanction:
            return jsonify({"msg": "Bu turdagi faol cheklov allaqachon mavjud"}), 409

    if payment_action != "none":
        payment_handler = (
            app.config.get("FINJOB_REFUND_PAYMENT") if payment_action == "refund_payer"
            else app.config.get("FINJOB_RELEASE_PAYMENT")
        )
        if not payment_handler:
            return jsonify({"msg": "To‘lov amali hozir mavjud emas"}), 503
        payment_ok, payment_message, _ = payment_handler(job_id)
        if not payment_ok:
            return jsonify({"msg": payment_message or "To‘lov chorasi bajarilmadi"}), 400

    if job_action == "block":
        held = db.q("SELECT id FROM payments WHERE job_id=? AND status='held' LIMIT 1", (job_id,)).fetchone()
        if held:
            return jsonify({"msg": "Ishda escrow to‘lovi bor. Avval pulni qaytarish yoki to‘lovni alohida hal qilish kerak."}), 409
        db.q(
            "UPDATE jobs SET status='blocked',finished_at=NULL,owner_finished=0,worker_finished=0 WHERE id=?",
            (job_id,)
        ).close()

    if sanction_type != "none":
        block_now = datetime.datetime.now(datetime.timezone.utc)
        expires_at = (block_now + datetime.timedelta(minutes=sanction_duration)).isoformat() if sanction_duration else None
        block_result = db.q(
            """INSERT INTO user_blocks(user_id,block_type,reason,duration_minutes,created_at,expires_at,active,created_by)
               VALUES(?,?,?,?,?,?,1,?)""",
            (sanction_user_id, sanction_type, f"Shikoyat #{report_id}: {response}"[:2000],
             sanction_duration, block_now.isoformat(), expires_at, request.uid)
        )
        block_result.close()
        if sanction_type == "full":
            db.q("UPDATE users SET is_blocked=1 WHERE id=?", (sanction_user_id,)).close()
        create_notification(
            sanction_user_id, "account_moderation", "Hisobingizga cheklov qo‘yildi",
            f"Shikoyat #{report_id} bo‘yicha {BLOCK_TYPE_LABELS[sanction_type]} qo‘llandi. Sabab: {response}.",
            "/appeals"
        )

    db.q(
        """UPDATE reports SET status=?,admin_response=?,decision=?,payment_action=?,job_action=?,
                  notify_target=?,sanction_user_id=?,sanction_type=?,sanction_duration_minutes=?
           WHERE id=?""",
        (status, response, decision, payment_action, job_action, notify_target,
         sanction_user_id, sanction_type, sanction_duration, report_id)
    ).close()

    if is_final:
        effects = []
        if payment_action == "refund_payer":
            effects.append("Escrowdagi to‘lov buyurtmachiga qaytarildi.")
        elif payment_action == "release_to_worker":
            effects.append("Escrowdagi to‘lov ijrochiga o‘tkazildi.")
        if job_action == "block":
            effects.append("Ish bloklandi.")
        if sanction_type != "none":
            effects.append(f"{BLOCK_TYPE_LABELS[sanction_type]} qo‘llandi.")
        summary = f"Shikoyat #{report_id} bo‘yicha qaror: {decision}. {response} " + " ".join(effects)
        title = "Shikoyat bo‘yicha yakuniy qaror"
        for uid in {reporter_id, reported_user_id} - {None}:
            create_notification(uid, "report_update", title, summary.strip(), "/jobs")
    if notify_target != "none":
        target_ids = []
        if notify_target in {"reporter", "both"} and reporter_id:
            target_ids.append(reporter_id)
        if notify_target in {"reported", "both"} and reported_user_id:
            target_ids.append(reported_user_id)
        for uid in set(target_ids):
            create_notification(uid, "report_warning", "Shikoyat bo‘yicha ogohlantirish",
                                response, "/jobs")

    admin_audit(
        "report_decision", "report", report_id,
        f"status={status}; decision={decision}; payment={payment_action}; job={job_action}; "
        f"notify={notify_target}; sanction={sanction_type}:{sanction_user_id}"
    )
    return jsonify({
        "msg": "Shikoyat bo‘yicha qaror va tanlangan choralar saqlandi.",
        "status": status, "decision": decision, "payment_action": payment_action,
        "job_action": job_action, "notify_target": notify_target,
        "sanction_type": sanction_type, "sanction_user_id": sanction_user_id
    })

@app.route("/admin/user/<int:user_id>/blocks")
@admin_required
def admin_user_blocks(user_id):
    target=db.q("SELECT id,username,role FROM users WHERE id=?",(user_id,)).fetchone()
    if not target:
        return jsonify({"msg":"Foydalanuvchi topilmadi"}),404
    blocks=db.q(
        """SELECT b.id,b.user_id,b.block_type,b.reason,b.duration_minutes,b.created_at,b.expires_at,b.active,b.created_by,b.lifted_at,b.lifted_by,u.username
           FROM user_blocks b LEFT JOIN users u ON u.id=b.created_by
           WHERE b.user_id=? ORDER BY b.id DESC LIMIT 100""",(user_id,)
    ).fetchall()
    return jsonify({"user":{"id":target[0],"username":target[1],"role":target[2]},
        "blocks":[{**_block_payload(x[:11]),"created_by_username":x[11] or "—"} for x in blocks]})


@app.route("/admin/blocks")
@admin_required
def admin_blocks():
    search=str(request.args.get("q","")).strip()[:100]
    status=str(request.args.get("status","active")).strip().lower()
    where=[]
    params=[]
    if search:
        where.append("(u.username LIKE ? OR b.reason LIKE ? OR b.block_type LIKE ?)")
        like=f"%{search}%"; params += [like,like,like]
    if status=="active":
        where.append("(b.active=1 AND (b.expires_at IS NULL OR b.expires_at>?))")
        params.append(datetime.datetime.now(datetime.timezone.utc).isoformat())
    elif status=="lifted":
        where.append("b.active=0")
    clause=" WHERE "+" AND ".join(where) if where else ""
    items=db.q(
        f"""SELECT b.id,b.user_id,u.username,b.block_type,b.reason,b.duration_minutes,b.created_at,b.expires_at,b.active,
                   a.username
            FROM user_blocks b
            JOIN users u ON u.id=b.user_id
            LEFT JOIN users a ON a.id=b.created_by
            {clause}
            ORDER BY b.id DESC LIMIT 150""",tuple(params)
    ).fetchall()
    return jsonify({"items":[
        {"id":x[0],"user_id":x[1],"username":x[2],"block_type":x[3],"block_label":BLOCK_TYPE_LABELS.get(x[3],x[3]),
         "reason":x[4],"duration_minutes":x[5],"created_at":x[6],"expires_at":x[7],"active":bool(x[8]),"admin_username":x[9] or "—"}
        for x in items
    ]})


@app.route("/admin/user/<int:user_id>/block", methods=["POST"])
@admin_required
def admin_create_block(user_id):
    data=request.json or {}
    block_type=str(data.get("block_type","")).strip().lower()
    reason=str(data.get("reason","")).strip()
    duration_raw=data.get("duration_minutes")
    if block_type not in BLOCK_TYPE_LABELS:
        return jsonify({"msg":"Block turi noto‘g‘ri"}),400
    if not reason or len(reason)>2000:
        return jsonify({"msg":"Block sababi 1–2000 belgidan iborat bo‘lishi kerak"}),400
    if user_id==int(request.uid):
        return jsonify({"msg":"O‘zingizni bloklay olmaysiz"}),400
    target=db.q("SELECT id,username,role FROM users WHERE id=?",(user_id,)).fetchone()
    if not target:
        return jsonify({"msg":"Foydalanuvchi topilmadi"}),404
    if target[2]=="admin":
        return jsonify({"msg":"Administrator hisobini bloklash mumkin emas"}),400
    duration=None
    if duration_raw not in (None,"","null"):
        try: duration=int(duration_raw)
        except (TypeError,ValueError): return jsonify({"msg":"Muddat noto‘g‘ri"}),400
        if duration<1 or duration>525600: return jsonify({"msg":"Muddat 1 daqiqadan 365 kungacha bo‘lishi kerak"}),400
    now=datetime.datetime.now(datetime.timezone.utc)
    expires=(now+datetime.timedelta(minutes=duration)).isoformat() if duration else None
    existing=_active_block_row(user_id,block_type)
    if existing:
        return jsonify({"msg":"Bu turdagi faol block allaqachon mavjud","block_id":existing[0]}),409
    result=db.q(
        """INSERT INTO user_blocks(user_id,block_type,reason,duration_minutes,created_at,expires_at,active,created_by)
           VALUES(?,?,?,?,?,?,1,?)""",
        (user_id,block_type,reason,duration,now.isoformat(),expires,request.uid)
    )
    block_id=result.lastrowid; result.close()
    if block_type == "full":
        db.q("UPDATE users SET is_blocked=1 WHERE id=?", (user_id,)).close()
    admin_audit("user_block_created","user",user_id,f"{block_type}: {reason}")
    deadline="muddatsiz" if not expires else expires
    create_notification(
        user_id,"account_moderation","Hisobingizga cheklov qo‘yildi",
        f"{BLOCK_TYPE_LABELS[block_type]} qo‘yildi. Sabab: {reason}. Muddati: {deadline}. Appeal yuborish uchun Appeals bo‘limiga kiring.",
        "/appeals"
    )
    return jsonify({"msg":"Block qo‘yildi","block_id":block_id,"expires_at":expires}),201


@app.route("/admin/block/<int:block_id>", methods=["PATCH"])
@admin_required
def admin_update_block(block_id):
    block=db.q("SELECT id,user_id,block_type,active FROM user_blocks WHERE id=?",(block_id,)).fetchone()
    if not block:
        return jsonify({"msg":"Block topilmadi"}),404
    data = request.json or {}
    action = str(data.get("action", "")).strip().lower()
    if not block[3]:
        return jsonify({"msg": "Block allaqachon olib tashlangan"}), 409
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now = now_dt.isoformat()
    if action == "modify":
        try:
            duration = int(data.get("duration_minutes"))
        except (TypeError, ValueError):
            return jsonify({"msg": "Muddatni daqiqalarda kiriting"}), 400
        if duration < 1 or duration > 525600:
            return jsonify({"msg": "Yangi muddat 1 daqiqadan 365 kungacha bo‘lishi kerak"}), 400
        reason = str(data.get("reason", "")).strip()
        if not reason or len(reason) > 2000:
            return jsonify({"msg": "Yangi sabab 1–2000 belgidan iborat bo‘lishi kerak"}), 400
        expires_at = (now_dt + datetime.timedelta(minutes=duration)).isoformat()
        db.q("UPDATE user_blocks SET duration_minutes=?,expires_at=?,reason=? WHERE id=?",
             (duration, expires_at, reason, block_id)).close()
        admin_audit("user_block_modified", "user", block[1], f"block={block_id}; duration={duration}; {reason}")
        create_notification(block[1], "account_moderation", "Cheklov muddati yangilandi",
                            f"Cheklov muddati {duration} daqiqaga yangilandi. Sabab: {reason}", "/appeals")
        return jsonify({"msg": "Cheklov muddati va sababi yangilandi", "expires_at": expires_at})
    if action != "lift":
        return jsonify({"msg": "Lift yoki modify amalini tanlang"}), 400
    reason = str(data.get("reason", "")).strip()
    if len(reason) > 1000:
        return jsonify({"msg": "Sabab 1000 belgidan oshmasligi kerak"}), 400
    db.q("UPDATE user_blocks SET active=0,lifted_at=?,lifted_by=? WHERE id=?",(now,request.uid,block_id)).close()
    if block[2] == "full" and not _active_block_row(block[1], "full"):
        db.q("UPDATE users SET is_blocked=0 WHERE id=?", (block[1],)).close()
    admin_audit("user_block_lifted","user",block[1],f"block={block_id}:{block[2]}; {reason}")
    create_notification(block[1],"account_moderation","Cheklov olib tashlandi",
                        f"{BLOCK_TYPE_LABELS.get(block[2],block[2])} administrator tomonidan olib tashlandi." + (f" Sabab: {reason}" if reason else ""),"/appeals")
    return jsonify({"msg":"Block olib tashlandi"})


@app.route("/appeals")
@auth
def get_appeals():
    blocks=_active_block_row(request.uid)
    appeals=db.q(
        """SELECT a.id,a.block_id,a.user_id,a.appeal_text,a.status,a.admin_response,a.created_at,a.reviewed_at,a.reviewed_by,
                  b.block_type,b.reason,b.created_at,b.expires_at,u.username
           FROM appeals a JOIN user_blocks b ON b.id=a.block_id
           LEFT JOIN users u ON u.id=a.reviewed_by
           WHERE a.user_id=? ORDER BY a.id DESC LIMIT 100""",(request.uid,)
    ).fetchall()
    return jsonify({
        "active_blocks":[_block_payload(x) for x in blocks],
        "appeals":[{"id":x[0],"block_id":x[1],"user_id":x[2],"appeal_text":x[3],"status":x[4],"admin_response":x[5] or "",
                    "created_at":x[6],"reviewed_at":x[7],"reviewed_by_username":x[8] or "—",
                    "block_type":x[9],"block_label":BLOCK_TYPE_LABELS.get(x[9],x[9]),"block_reason":x[10],
                    "block_created_at":x[11],"block_expires_at":x[12]}
                   for x in appeals]
    })


@app.route("/appeals", methods=["POST"])
@auth
def create_appeal():
    data=request.json or {}
    try: block_id=int(data.get("block_id"))
    except (TypeError,ValueError): return jsonify({"msg":"Block ID noto‘g‘ri"}),400
    appeal_text=str(data.get("appeal_text","")).strip()
    if len(appeal_text)<10 or len(appeal_text)>4000:
        return jsonify({"msg":"Appeal matni 10–4000 belgidan iborat bo‘lishi kerak"}),400
    block=db.q("SELECT id,user_id,block_type,active,expires_at FROM user_blocks WHERE id=?",(block_id,)).fetchone()
    if not block or block[1]!=request.uid:
        return jsonify({"msg":"Block topilmadi"}),404
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    if not block[3] or (block[4] and block[4]<=now):
        return jsonify({"msg":"Bu block endi faol emas"}),409
    existing=db.q("SELECT id FROM appeals WHERE block_id=? AND status IN ('open','reviewing') LIMIT 1",(block_id,)).fetchone()
    if existing:
        return jsonify({"msg":"Bu block uchun appeal allaqachon ko‘rib chiqilmoqda"}),409
    result=db.q(
        "INSERT INTO appeals(block_id,user_id,appeal_text,status,created_at) VALUES(?,?,?,?,?)",
        (block_id,request.uid,appeal_text,"open",now)
    )
    appeal_id=result.lastrowid; result.close()
    admin_audit("appeal_created","user",request.uid,f"block={block_id}")
    for admin in db.q("SELECT id FROM users WHERE role='admin'").fetchall():
        create_notification(admin[0],"appeal","Yangi appeal",f"Foydalanuvchidan yangi appeal: block #{block_id}.","/admin")
    return jsonify({"msg":"Appeal yuborildi","appeal_id":appeal_id}),201


@app.route("/admin/appeals")
@admin_required
def admin_appeals():
    status=str(request.args.get("status","all")).strip().lower()
    search=str(request.args.get("q","")).strip()[:100]
    where=[]; params=[]
    if status!="all":
        if status not in ("open","reviewing","approved","rejected","modified"): return jsonify({"msg":"Appeal status noto‘g‘ri"}),400
        where.append("a.status=?"); params.append(status)
    if search:
        like=f"%{search}%"
        where.append("(u.username LIKE ? OR a.appeal_text LIKE ? OR b.reason LIKE ? OR b.block_type LIKE ?)")
        params += [like,like,like,like]
    clause=" WHERE "+" AND ".join(where) if where else ""
    items=db.q(
        f"""SELECT a.id,a.block_id,a.user_id,u.username,a.appeal_text,a.status,a.admin_response,
                   a.created_at,a.reviewed_at,b.block_type,b.reason,b.duration_minutes,b.expires_at,
                   reviewer.username
            FROM appeals a
            JOIN users u ON u.id=a.user_id
            JOIN user_blocks b ON b.id=a.block_id
            LEFT JOIN users reviewer ON reviewer.id=a.reviewed_by
            {clause} ORDER BY a.id DESC LIMIT 200""",tuple(params)
    ).fetchall()
    return jsonify({"items":[
        {"id":x[0],"block_id":x[1],"user_id":x[2],"username":x[3],"appeal_text":x[4],"status":x[5],
         "admin_response":x[6] or "","created_at":x[7],"reviewed_at":x[8],"block_type":x[9],
         "block_label":BLOCK_TYPE_LABELS.get(x[9],x[9]),"block_reason":x[10],"duration_minutes":x[11],
         "expires_at":x[12],"reviewer_username":x[13] or "—"}
        for x in items
    ]})


@app.route("/admin/appeal/<int:appeal_id>", methods=["PATCH"])
@admin_required
def admin_review_appeal(appeal_id):
    data = request.json or {}
    status = str(data.get("status", "")).strip().lower()
    response = str(data.get("admin_response", "")).strip()
    block_action = str(data.get("block_action", "")).strip().lower()
    duration_raw = data.get("duration_minutes", 1440)
    new_block_type = str(data.get("new_block_type", "")).strip().lower()

    if status not in ("reviewing", "approved", "rejected", "modified"):
        return jsonify({"msg": "Appeal status noto‘g‘ri"}), 400
    if len(response) > 3000:
        return jsonify({"msg": "Admin javobi 3000 belgidan oshmasligi kerak"}), 400

    row = db.q("SELECT id,user_id,block_id,status FROM appeals WHERE id=?", (appeal_id,)).fetchone()
    if not row:
        return jsonify({"msg": "Appeal topilmadi"}), 404
    if row[3] in ("approved", "rejected", "modified") and status != row[3]:
        return jsonify({"msg": "Yakunlangan appealni qayta o‘zgartirib bo‘lmaydi"}), 409

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now = now_dt.isoformat()
    if status == "modified":
        if block_action not in ("reduce_duration", "change_type"):
            return jsonify({"msg": "Cheklovni qisqartirish yoki yengilroq turga almashtirishni tanlang"}), 400
        block = db.q(
            "SELECT id,user_id,block_type,reason,active,expires_at,duration_minutes FROM user_blocks WHERE id=?",
            (row[2],)
        ).fetchone()
        if not block or not block[4] or (block[5] and block[5] <= now):
            return jsonify({"msg": "Faol cheklov topilmadi; uni o‘zgartirib bo‘lmaydi"}), 409
        try:
            duration = int(duration_raw)
        except (TypeError, ValueError):
            return jsonify({"msg": "Yangi cheklov muddati noto‘g‘ri"}), 400
        if duration < 1 or duration > 525600:
            return jsonify({"msg": "Yangi muddat 1 daqiqadan 365 kungacha bo‘lishi kerak"}), 400
        updated_type = block[2]
        if block_action == "change_type":
            lighter_types = {"chat", "job_creation", "job_accept", "proposal", "rating", "withdrawal"}
            if block[2] != "full":
                return jsonify({"msg": "Cheklov turini faqat to‘liq blokdan yengilroq cheklovga almashtirish mumkin"}), 400
            if new_block_type not in lighter_types:
                return jsonify({"msg": "Yengilroq cheklov turini tanlang"}), 400
            updated_type = new_block_type
        expires_at = (now_dt + datetime.timedelta(minutes=duration)).isoformat()
        if block[5] and expires_at >= block[5]:
            return jsonify({"msg": "Yangi muddat mavjud cheklovning qolgan muddatidan qisqaroq bo‘lishi kerak"}), 400
        new_reason = block[3]
        if response:
            new_reason = (str(block[3] or "") + f" [Appeal #{appeal_id}: {response}]")[:2000]
        db.q(
            "UPDATE user_blocks SET block_type=?,reason=?,duration_minutes=?,expires_at=? WHERE id=?",
            (updated_type, new_reason, duration, expires_at, row[2])
        ).close()
        if block[2] == "full" and updated_type != "full" and not _active_block_row(block[1], "full"):
            db.q("UPDATE users SET is_blocked=0 WHERE id=?", (block[1],)).close()
        message = f"Cheklov yengillashtirildi: {BLOCK_TYPE_LABELS.get(updated_type, updated_type)}, {duration} daqiqa."
    elif status == "approved":
        db.q("UPDATE user_blocks SET active=0,lifted_at=?,lifted_by=? WHERE id=?", (now, request.uid, row[2])).close()
        block_row = db.q("SELECT user_id,block_type FROM user_blocks WHERE id=?", (row[2],)).fetchone()
        if block_row and block_row[1] == "full" and not _active_block_row(block_row[0], "full"):
            db.q("UPDATE users SET is_blocked=0 WHERE id=?", (block_row[0],)).close()
        message = "Appealingiz tasdiqlandi va ushbu cheklov olib tashlandi."
    elif status == "rejected":
        message = "Appealingiz rad etildi; cheklov saqlanadi."
    else:
        message = "Appealingiz administrator tomonidan ko‘rib chiqilmoqda."

    db.q("UPDATE appeals SET status=?,admin_response=?,reviewed_at=?,reviewed_by=? WHERE id=?",
         (status, response, now, request.uid, appeal_id)).close()
    admin_audit(
        "appeal_reviewed", "appeal", appeal_id,
        f"status={status}; block_action={block_action or 'none'}; new_type={new_block_type or 'same'}; duration={duration_raw}; {response}"
    )
    create_notification(
        row[1], "appeal", "Appeal bo‘yicha qaror",
        message + (f" Admin izohi: {response}" if response else ""), "/appeals"
    )
    return jsonify({"msg": "Appeal bo‘yicha qaror saqlandi", "status": status, "block_action": block_action})

@app.route("/admin/overview")
@admin_required
def admin_overview():
    users = db.q(
        """SELECT id, username, first_name, last_name, email, birthday, bio, skills, role, created_at,
                  average_rating, COALESCE(balance,0),
                  CASE WHEN EXISTS(
                      SELECT 1 FROM user_blocks ub
                      WHERE ub.user_id=users.id AND ub.active=1
                        AND (ub.expires_at IS NULL OR ub.expires_at>?)
                        AND ub.block_type='full'
                  ) THEN 1 ELSE 0 END,
                  COALESCE(email_verified,0),COALESCE(phone_verified,0),COALESCE(identity_verified,0)
           FROM users ORDER BY id DESC""",
        (datetime.datetime.now(datetime.timezone.utc).isoformat(),)
    ).fetchall()
    jobs = db.q(
        """SELECT j.id,j.title,j.price,j.currency,j.location,j.status,j.created_at,
                  u.username AS creator_username,w.username AS worker_username
           FROM jobs j
           LEFT JOIN users u ON u.id=j.user_id
           LEFT JOIN users w ON w.id=j.worker_id
           ORDER BY j.id DESC"""
    ).fetchall()
    services = db.q(
        """SELECT s.id,s.name,s.parent_id,p.name AS parent_name,s.created_by
           FROM services s
           LEFT JOIN services p ON p.id=s.parent_id
           ORDER BY s.id DESC"""
    ).fetchall()
    ratings = db.q(
        """SELECT r.id,r.job_id,r.score,r.comment,r.created_at,
                  f.username AS from_username,t.username AS to_username
           FROM ratings r
           LEFT JOIN users f ON f.id=r.from_user
           LEFT JOIN users t ON t.id=r.to_user
           ORDER BY r.id DESC"""
    ).fetchall()
    reports = db.q(
        """SELECT r.id,r.job_id,r.message_id,r.reason,r.details,r.status,r.created_at,
                  f.username AS reporter_username,t.username AS reported_username,
                  m.attachment_url,m.attachment_name,m.attachment_type,r.admin_response,r.decision,
                  r.payment_action,r.job_action,r.notify_target,r.sanction_user_id,r.sanction_type,r.sanction_duration_minutes,
                  r.reporter_id,r.reported_user_id
           FROM reports r
           LEFT JOIN users f ON f.id=r.reporter_id
           LEFT JOIN users t ON t.id=r.reported_user_id
           LEFT JOIN messages m ON m.id=r.message_id
           ORDER BY r.id DESC"""
    ).fetchall()
    commission_row=db.q("SELECT value FROM platform_settings WHERE key='commission_percent'").fetchone()
    commission_percent=float(commission_row[0]) if commission_row else 10.0
    return jsonify({
        "settings":{"commission_percent":commission_percent},
        "stats":{
            "users":len(users),"jobs":len(jobs),
            "active_jobs":sum(1 for j in jobs if str(j[5]).lower()=="active"),
            "finished_jobs":sum(1 for j in jobs if str(j[5]).lower()=="finished"),
            "services":len(services),"ratings":len(ratings),"reports":len(reports),
            "pending_reports":sum(1 for r in reports if str(r[5]).lower() in ("open","reviewing")),
            "blocked_jobs":sum(1 for j in jobs if str(j[5]).lower()=="blocked"),
            "admins":sum(1 for u in users if str(u[8]).lower()=="admin"),
            "blocked_users":sum(1 for u in users if int(u[12] or 0)==1),
        },
        "users":rows(users,["id","username","first_name","last_name","email","birthday","bio","skills","role","created_at","average_rating","balance","is_blocked","email_verified","phone_verified","identity_verified"]),
        "jobs":rows(jobs,["id","title","price","currency","location","status","created_at","creator_username","worker_username"]),
        "services":rows(services,["id","name","parent_id","parent_name","created_by"]),
        "ratings":rows(ratings,["id","job_id","score","comment","created_at","from_username","to_username"]),
        "reports":rows(reports,["id","job_id","message_id","reason","details","status","created_at","reporter_username","reported_username","attachment_url","attachment_name","attachment_type","admin_response","decision","payment_action","job_action","notify_target","sanction_user_id","sanction_type","sanction_duration_minutes","reporter_id","reported_user_id"]),
    })


@app.route("/admin/analytics")
@admin_required
def admin_analytics():
    payments = db.q(
        """SELECT status, COUNT(*), COALESCE(SUM(amount),0)
           FROM payments GROUP BY status"""
    ).fetchall()
    wallet = db.q(
        "SELECT COALESCE(balance,0), COALESCE(escrow_balance,0) FROM platform_wallet WHERE id=1"
    ).fetchone()
    tx = db.q(
        """SELECT type, COUNT(*),
                  COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END),0),
                  COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END),0)
           FROM wallet_transactions GROUP BY type"""
    ).fetchall()
    top_services = db.q(
        """SELECT COALESCE(s.name, NULLIF(j.custom_service,''), 'Noma'), COUNT(*)
           FROM jobs j
           LEFT JOIN services s ON s.id=j.service_id
           GROUP BY COALESCE(s.id, NULLIF(j.custom_service,''))
           ORDER BY COUNT(*) DESC LIMIT 8"""
    ).fetchall()
    return jsonify({
        "payments":[{"status":x[0],"count":x[1],"amount":float(x[2] or 0)} for x in payments],
        "wallet":{"balance":float(wallet[0] or 0) if wallet else 0,"escrow_balance":float(wallet[1] or 0) if wallet else 0},
        "transactions":[{"type":x[0],"count":x[1],"inflow":float(x[2] or 0),"outflow":float(x[3] or 0)} for x in tx],
        "top_services":[{"name":x[0],"total":x[1]} for x in top_services],
    })


@app.route("/admin/finance")
@admin_required
def admin_finance():
    transactions = db.q(
        """SELECT wt.id,wt.user_id,u.username,wt.type,wt.amount,wt.balance_after,wt.job_id,wt.description,wt.created_at
           FROM wallet_transactions wt
           LEFT JOIN users u ON u.id=wt.user_id
           ORDER BY wt.id DESC LIMIT 100"""
    ).fetchall()
    payments = db.q(
        """SELECT p.id,p.job_id,p.amount,p.currency,p.status,p.provider,p.created_at,p.paid_at,p.released_at,p.refunded_at,
                  payer.username,payee.username,j.status
           FROM payments p
           LEFT JOIN users payer ON payer.id=p.payer_id
           LEFT JOIN users payee ON payee.id=p.payee_id
           LEFT JOIN jobs j ON j.id=p.job_id
           ORDER BY p.id DESC LIMIT 100"""
    ).fetchall()
    wallet=db.q("SELECT COALESCE(balance,0),COALESCE(escrow_balance,0) FROM platform_wallet WHERE id=1").fetchone()
    return jsonify({
        "wallet":{"balance":float(wallet[0] or 0) if wallet else 0,"escrow_balance":float(wallet[1] or 0) if wallet else 0},
        "transactions":[
            {"id":x[0],"user_id":x[1],"username":x[2] or "—","type":x[3],"amount":float(x[4] or 0),
             "balance_after":float(x[5] or 0),"job_id":x[6],"description":x[7],"created_at":x[8]}
            for x in transactions
        ],
        "payments":[
            {"id":x[0],"job_id":x[1],"amount":float(x[2] or 0),"currency":x[3],"status":x[4],"provider":x[5],
             "created_at":x[6],"paid_at":x[7],"released_at":x[8],"refunded_at":x[9],
             "payer_username":x[10] or "—","payee_username":x[11] or "—","job_status":x[12] or ""}
            for x in payments
        ],
    })


@app.route("/admin/payment/<int:job_id>", methods=["PATCH"])
@admin_required
def admin_payment_action(job_id):
    data = request.json or {}
    action = str(data.get("action", "")).strip().lower()
    reason = str(data.get("reason", "")).strip()
    if action not in {"refund", "release"}:
        return jsonify({"msg": "Qaytarish yoki ijrochiga o‘tkazishni tanlang"}), 400
    if len(reason) < 5 or len(reason) > 2000:
        return jsonify({"msg": "Moliyaviy qaror sababi 5–2000 belgidan iborat bo‘lishi kerak"}), 400
    payment = db.q(
        """SELECT p.status,j.status,j.user_id,j.worker_id,j.title
           FROM payments p JOIN jobs j ON j.id=p.job_id WHERE p.job_id=?""",
        (job_id,)
    ).fetchone()
    if not payment:
        return jsonify({"msg": "Ish yoki to‘lov topilmadi"}), 404
    payment_status, job_status, owner_id, worker_id, title = payment
    if payment_status != "held":
        return jsonify({"msg": "Faqat escrowda ushlab turilgan to‘lovga amal bajarish mumkin"}), 409
    if action == "release" and job_status not in {"pending_finish", "finished"}:
        return jsonify({"msg": "To‘lovni chiqarish uchun ish yakunlash bosqichida bo‘lishi kerak"}), 409

    handler = app.config.get("FINJOB_REFUND_PAYMENT" if action == "refund" else "FINJOB_RELEASE_PAYMENT")
    if not handler:
        return jsonify({"msg": "To‘lov amali hozir mavjud emas"}), 503
    ok, message, _ = handler(job_id)
    if not ok:
        return jsonify({"msg": message or "To‘lov bo‘yicha amal bajarilmadi"}), 400

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if action == "refund":
        db.q("UPDATE jobs SET status='blocked',finished_at=NULL,owner_finished=0,worker_finished=0 WHERE id=?", (job_id,)).close()
        summary = f"«{title}» bo‘yicha escrowdagi to‘lov buyurtmachiga qaytarildi. Sabab: {reason}"
    else:
        db.q("UPDATE jobs SET status='finished',finished_at=COALESCE(finished_at,?) WHERE id=?", (now, job_id)).close()
        summary = f"«{title}» bo‘yicha to‘lov ijrochiga o‘tkazildi. Sabab: {reason}"
    for uid in {owner_id, worker_id} - {None}:
        create_notification(uid, "admin_payment_decision", "To‘lov bo‘yicha admin qarori", summary, "/payments")
    admin_audit("admin_payment_action", "job", job_id, f"action={action}; reason={reason}")
    return jsonify({"msg": "To‘lov bo‘yicha qaror bajarildi", "action": action})


@app.route("/admin/audit-log")
@admin_required
def admin_audit_log():
    try:
        page=max(1,int(request.args.get("page",1)))
        limit=min(100,max(10,int(request.args.get("limit",25))))
    except (TypeError,ValueError):
        return jsonify({"msg":"Pagination parametrlari noto‘g‘ri"}),400
    search=str(request.args.get("q","")).strip()[:100]
    where=""
    params=[]
    if search:
        where="WHERE a.action LIKE ? OR a.target_type LIKE ? OR a.details LIKE ? OR u.username LIKE ?"
        value=f"%{search}%"
        params=[value,value,value,value]
    total=db.q(
        f"SELECT COUNT(*) FROM admin_audit_log a LEFT JOIN users u ON u.id=a.admin_id {where}",
        tuple(params)
    ).fetchone()[0]
    items=db.q(
        f"""SELECT a.id,a.action,a.target_type,a.target_id,a.details,a.created_at,u.username
            FROM admin_audit_log a
            LEFT JOIN users u ON u.id=a.admin_id
            {where}
            ORDER BY a.id DESC LIMIT ? OFFSET ?""",
        tuple(params+[limit,(page-1)*limit])
    ).fetchall()
    return jsonify({
        "items":rows(items,["id","action","target_type","target_id","details","created_at","admin_username"]),
        "page":page,"limit":limit,"total":total,"pages":max(1,(total+limit-1)//limit)
    })


@app.route("/admin/search")
@admin_required
def admin_search():
    q=str(request.args.get("q","")).strip()[:100]
    if len(q)<2:
        return jsonify({"users":[],"jobs":[],"services":[],"reports":[]})
    like=f"%{q}%"
    users=db.q(
        """SELECT id,username,first_name,last_name,email,role,
                  CASE WHEN EXISTS(
                      SELECT 1 FROM user_blocks ub
                      WHERE ub.user_id=users.id AND ub.active=1
                        AND (ub.expires_at IS NULL OR ub.expires_at>?)
                        AND ub.block_type='full'
                  ) THEN 1 ELSE 0 END
           FROM users WHERE username LIKE ? OR email LIKE ? OR first_name LIKE ? OR last_name LIKE ?
           ORDER BY id DESC LIMIT 12""",
        (datetime.datetime.now(datetime.timezone.utc).isoformat(),like,like,like,like)
    ).fetchall()
    jobs=db.q(
        """SELECT j.id,j.title,j.status,u.username
           FROM jobs j LEFT JOIN users u ON u.id=j.user_id
           WHERE j.title LIKE ? OR j.description LIKE ? OR u.username LIKE ?
           ORDER BY j.id DESC LIMIT 12""",(like,like,like)
    ).fetchall()
    services=db.q("SELECT id,name,parent_id FROM services WHERE name LIKE ? ORDER BY id DESC LIMIT 12",(like,)).fetchall()
    reports=db.q(
        """SELECT r.id,r.reason,r.details,r.status,u.username
           FROM reports r LEFT JOIN users u ON u.id=r.reporter_id
           WHERE r.reason LIKE ? OR r.details LIKE ? OR u.username LIKE ?
           ORDER BY r.id DESC LIMIT 12""",(like,like,like)
    ).fetchall()
    return jsonify({
        "users":[{"id":x[0],"username":x[1],"name":f"{x[2] or ''} {x[3] or ''}".strip(),"email":x[4],"role":x[5],"is_blocked":int(x[6] or 0)} for x in users],
        "jobs":[{"id":x[0],"title":x[1],"status":x[2],"username":x[3] or ""} for x in jobs],
        "services":[{"id":x[0],"name":x[1],"parent_id":x[2]} for x in services],
        "reports":[{"id":x[0],"reason":x[1],"details":x[2],"status":x[3],"username":x[4] or ""} for x in reports],
    })


@app.route("/admin/user/<int:user_id>/status", methods=["PATCH"])
@admin_required
def admin_user_status(user_id):
    value=(request.json or {}).get("is_blocked")
    blocked=value is True or str(value).lower() in ("1","true","yes")
    if user_id==int(request.uid):
        return jsonify({"msg":"O‘zingizni bloklay olmaysiz."}),400
    target=db.q("SELECT id,role,username FROM users WHERE id=?",(user_id,)).fetchone()
    if not target:
        return jsonify({"msg":"Foydalanuvchi topilmadi."}),404
    if target[1]=="admin" and blocked:
        return jsonify({"msg":"Administrator hisobini bloklash mumkin emas."}),400
    existing=_active_block_row(user_id,"full")
    if blocked:
        if existing:
            return jsonify({"msg":"To‘liq block allaqachon mavjud.","block_id":existing[0]}),409
        now=datetime.datetime.now(datetime.timezone.utc)
        result=db.q(
            "INSERT INTO user_blocks(user_id,block_type,reason,duration_minutes,created_at,expires_at,active,created_by) VALUES(?,?,?,?,?,?,1,?)",
            (user_id,"full","Administrator tomonidan berilgan to‘liq blok.",None,now.isoformat(),None,request.uid)
        )
        block_id=result.lastrowid; result.close()
        db.q("UPDATE users SET is_blocked=1 WHERE id=?", (user_id,)).close()
        admin_audit("user_block_created","user",user_id,f"full: legacy endpoint")
        create_notification(user_id,"account_moderation","Hisobingiz to‘liq bloklandi","Administrator hisobingizni to‘liq blokladi. Sabab: Administrator tomonidan berilgan to‘liq blok. Appeal yuborish uchun Appeals bo‘limiga kiring.","/appeals")
        return jsonify({"msg":"Foydalanuvchi bloklandi.","block_id":block_id})
    if not existing:
        db.q("UPDATE users SET is_blocked=0 WHERE id=?",(user_id,)).close()
        return jsonify({"msg":"Faol to‘liq block topilmadi."})
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    db.q("UPDATE user_blocks SET active=0,lifted_at=?,lifted_by=? WHERE id=?",(now,request.uid,existing[0])).close()
    if not _active_block_row(user_id, "full"):
        db.q("UPDATE users SET is_blocked=0 WHERE id=?", (user_id,)).close()
    admin_audit("user_block_lifted","user",user_id,f"block={existing[0]}: legacy endpoint")
    create_notification(user_id,"account_moderation","To‘liq block olib tashlandi","Administrator to‘liq blokni olib tashladi.","/appeals")
    return jsonify({"msg":"Foydalanuvchi qayta faollashtirildi."})


@app.route("/admin/settings/commission", methods=["PATCH"])
@admin_required
def admin_update_commission():
    d = request.json or {}
    try:
        value = float(d.get("commission_percent"))
    except (TypeError, ValueError):
        return jsonify({"msg": "Komissiya foizi noto‘g‘ri kiritildi."}), 400

    if not math.isfinite(value) or value < 0 or value > 100:
        return jsonify({"msg": "Komissiya 0% dan 100% gacha bo‘lishi kerak."}), 400

    value = round(value, 2)
    db.q(
        """INSERT INTO platform_settings(key,value) VALUES('commission_percent',?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (str(value),)
    ).close()
    admin_audit("commission_update","settings",None,f"commission_percent={value:g}")

    return jsonify({"ok": True, "msg": f"Platforma komissiyasi {value:g}% ga o‘zgartirildi.", "commission_percent": value})


@app.route("/admin/user-role", methods=["PATCH"])
@admin_required
def admin_user_role():
    d = request.json or {}
    user_id = d.get("user_id")
    role = str(d.get("role", "")).strip().lower()
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({"msg": "Foydalanuvchi ID raqami noto‘g‘ri."}), 400

    if role not in ("user", "admin"):
        return jsonify({"msg": "Foydalanuvchi ID raqami va roli to‘g‘ri ko‘rsatilishi kerak."}), 400

    if user_id == int(request.uid):
        return jsonify({"msg": "Bu yerdan o‘zingizning administrator rolingizni o‘zgartira olmaysiz."}), 400

    target = db.q("SELECT id, role FROM users WHERE id=?", (user_id,)).fetchone()
    if not target:
        return jsonify({"msg": "Foydalanuvchi topilmadi."}), 404

    db.q("UPDATE users SET role=?, token_version=COALESCE(token_version,0)+1 WHERE id=?", (role, user_id)).close()
    admin_audit("user_role_update","user",user_id,f"role={role}")
    return jsonify({"msg": "Foydalanuvchi roli yangilandi."})


@app.route("/admin/user/<int:user_id>", methods=["PATCH"])
@admin_required
def admin_update_user(user_id):
    d = request.json or {}

    target = db.q(
        "SELECT id, username, email, role FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not target:
        return jsonify({"msg": "Foydalanuvchi topilmadi."}), 404

    username = str(d.get("username", "")).strip()
    email = str(d.get("email", "")).strip().lower()
    first_name = str(d.get("first_name", "")).strip()
    last_name = str(d.get("last_name", "")).strip()
    birthday = str(d.get("birthday", "")).strip()
    bio = str(d.get("bio", "")).strip()
    skills = str(d.get("skills", "")).strip()
    password = str(d.get("password", ""))

    if not username or not email:
        return jsonify({"msg": "Foydalanuvchi nomi va elektron pochta bo‘sh bo‘lishi mumkin emas."}), 400
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
        return jsonify({"msg": "Foydalanuvchi nomi 3–32 belgidan iborat bo‘lishi kerak."}), 400
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
        return jsonify({"msg": "Elektron pochta manzili noto‘g‘ri."}), 400
    if len(first_name) > 100 or len(last_name) > 100 or len(birthday) > 32 or len(bio) > 2000 or len(skills) > 2000:
        return jsonify({"msg": "Foydalanuvchi ma'lumotlaridan biri juda uzun."}), 400

    duplicate = db.q(
        """SELECT id FROM users
           WHERE (username=? OR email=?) AND id!=?""",
        (username, email, user_id)
    ).fetchone()

    if duplicate:
        return jsonify({"msg": "Bu foydalanuvchi nomi yoki elektron pochta boshqa foydalanuvchida mavjud."}), 409

    if password:
        if len(password) < 8 or len(password) > 256:
            return jsonify({"msg": "Yangi parol 8–256 belgidan iborat bo‘lishi kerak."}), 400

        hashed = generate_password_hash(password)
        db.q(
            """UPDATE users
               SET username=?, email=?, first_name=?, last_name=?, birthday=?,
                   bio=?, skills=?, password=?, token_version=COALESCE(token_version,0)+1
               WHERE id=?""",
            (username, email, first_name, last_name, birthday, bio, skills, hashed, user_id)
        ).close()
    else:
        db.q(
            """UPDATE users
               SET username=?, email=?, first_name=?, last_name=?, birthday=?,
                   bio=?, skills=?
               WHERE id=?""",
            (username, email, first_name, last_name, birthday, bio, skills, user_id)
        ).close()

    admin_audit("user_update","user",user_id,f"@{username}")
    return jsonify({"msg": "Foydalanuvchi ma'lumotlari yangilandi."})


@app.route("/admin/user/<int:user_id>", methods=["DELETE"])
@admin_required
def admin_delete_user(user_id):
    deletion_reason = str((request.get_json(silent=True) or {}).get("reason", "")).strip()
    if len(deletion_reason) > 1000:
        return jsonify({"msg": "O‘chirish sababi 1000 belgidan oshmasligi kerak"}), 400
    if user_id == int(request.uid):
        return jsonify({"msg": "O'zingizni o'chira olmaysiz."}), 400

    target = db.q("SELECT id, role FROM users WHERE id=?", (user_id,)).fetchone()
    if not target:
        return jsonify({"msg": "Foydalanuvchi topilmadi."}), 404

    if target[1] == "admin":
        return jsonify({"msg": "Boshqa administratorni o‘chirish uchun avval uning rolini foydalanuvchiga o‘zgartiring."}), 400

    held_payment = db.q(
        "SELECT id FROM payments WHERE (payer_id=? OR payee_id=?) AND status='held' LIMIT 1",
        (user_id, user_id),
    ).fetchone()
    if held_payment:
        return jsonify({"msg": "Bu foydalanuvchiga tegishli waiting to‘lovi mavjud. Avval ishni refund yoki yakunlash orqali hal qiling."}), 409

    profile_files_to_remove = []
    profile_row = db.q("SELECT avatar_url FROM users WHERE id=?", (user_id,)).fetchone()
    if profile_row and profile_row[0]:
        profile_files_to_remove.append(profile_row[0])

    for row in db.q(
        "SELECT file_url,image_url FROM portfolio_items WHERE user_id=?",
        (user_id,),
    ).fetchall():
        profile_files_to_remove.extend([row[0], row[1]])

    for row in db.q(
        """SELECT m.attachment_url
           FROM messages m
           LEFT JOIN jobs j ON j.id=m.job_id
           WHERE (m.sender_id=? OR m.receiver_id=? OR j.user_id=? OR j.worker_id=?)
             AND m.attachment_url!=''""",
        (user_id, user_id, user_id, user_id),
    ).fetchall():
        if row[0]:
            profile_files_to_remove.append(row[0])

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM messages WHERE sender_id=? OR receiver_id=?", (user_id, user_id))
        cur.execute("DELETE FROM ratings WHERE from_user=? OR to_user=?", (user_id, user_id))
        cur.execute("DELETE FROM job_proposals WHERE worker_id=? OR job_id IN (SELECT id FROM jobs WHERE user_id=? OR worker_id=?)", (user_id, user_id, user_id))
        cur.execute("DELETE FROM favorites WHERE user_id=? OR (target_type='user' AND target_id=?) OR (target_type='job' AND target_id IN (SELECT id FROM jobs WHERE user_id=? OR worker_id=?))", (user_id, user_id, user_id, user_id))
        cur.execute("DELETE FROM portfolio_items WHERE user_id=?", (user_id,))
        cur.execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
        cur.execute("DELETE FROM reports WHERE reporter_id=? OR reported_user_id=? OR job_id IN (SELECT id FROM jobs WHERE user_id=? OR worker_id=?)", (user_id, user_id, user_id, user_id))
        cur.execute("DELETE FROM appeals WHERE user_id=? OR block_id IN (SELECT id FROM user_blocks WHERE user_id=?)", (user_id, user_id))
        cur.execute("DELETE FROM user_blocks WHERE user_id=?", (user_id,))
        cur.execute("DELETE FROM typing_states WHERE user_id=?", (user_id,))
        cur.execute("DELETE FROM job_services WHERE job_id IN (SELECT id FROM jobs WHERE user_id=? OR worker_id=?)", (user_id, user_id))
        cur.execute("DELETE FROM jobs WHERE user_id=? OR worker_id=?", (user_id, user_id))
        cur.execute("UPDATE services SET created_by=NULL WHERE created_by=?", (user_id,))
        cur.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for stored_url in set(profile_files_to_remove):
        _remove_stored_upload(stored_url, "/uploads/profile_pictures/", PROFILE_UPLOAD_DIR)
        _remove_stored_upload(stored_url, "/uploads/portfolio/", PORTFOLIO_UPLOAD_DIR)
        _remove_stored_upload(stored_url, "/uploads/chat/", CHAT_UPLOAD_DIR)

    admin_audit("user_delete","user",user_id,("Sabab: " + deletion_reason) if deletion_reason else "Admin foydalanuvchini o‘chirdi.")
    return jsonify({"msg": "Foydalanuvchi va unga bog'liq ma'lumotlar o'chirildi."})


@app.route("/admin/job/<int:job_id>", methods=["PATCH"])
@admin_required
def admin_update_job(job_id):
    d = request.json or {}
    status = str(d.get("status", "")).strip().lower()
    reason = str(d.get("reason", "")).strip()
    if len(reason) > 2000:
        return jsonify({"msg": "Sabab 2000 belgidan oshmasligi kerak."}), 400
    allowed = {"active", "payment_pending", "accepted", "pending_finish", "finished", "blocked"}

    if status not in allowed:
        return jsonify({"msg": "Ish holati noto‘g‘ri."}), 400

    job = db.q("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi."}), 404

    job_state = db.q("SELECT user_id,worker_id,title,status FROM jobs WHERE id=?", (job_id,)).fetchone()
    owner_id, worker_id, job_title, old_status = job_state if job_state else (None, None, "", "")
    held_payment = db.q(
        "SELECT id FROM payments WHERE job_id=? AND status='held' LIMIT 1",
        (job_id,),
    ).fetchone()

    if status in {"payment_pending", "accepted", "pending_finish", "finished"} and not worker_id:
        return jsonify({"msg": "Bu holatni tanlash uchun avval ishga bajaruvchi biriktirilishi kerak."}), 400

    if held_payment and status in {"active", "blocked"}:
        refund_payment = app.config.get("FINJOB_REFUND_PAYMENT")
        if refund_payment:
            ok, message, _ = refund_payment(job_id)
            if not ok:
                return jsonify({"msg": message}), 400

    if status == "active":
        db.q("UPDATE jobs SET status='active', worker_id=NULL, finished_at=NULL WHERE id=?", (job_id,)).close()
    elif status == "payment_pending":
        db.q("UPDATE jobs SET status='payment_pending', finished_at=NULL WHERE id=?", (job_id,)).close()
    elif status == "accepted":
        db.q("UPDATE jobs SET status='accepted', finished_at=NULL WHERE id=?", (job_id,)).close()
    elif status == "pending_finish":
        db.q("UPDATE jobs SET status='pending_finish', finished_at=NULL WHERE id=?", (job_id,)).close()
    elif status == "blocked":
        db.q(
            "UPDATE jobs SET status='blocked', finished_at=NULL, owner_finished=0, worker_finished=0 WHERE id=?",
            (job_id,),
        ).close()
    else:
        finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.q("UPDATE jobs SET status='finished', finished_at=? WHERE id=?", (finished_at, job_id)).close()
        release_payment = app.config.get("FINJOB_RELEASE_PAYMENT")
        if release_payment:
            ok, message, _ = release_payment(job_id)
            if not ok:
                db.q("UPDATE jobs SET status='accepted', finished_at=NULL WHERE id=?", (job_id,)).close()
                return jsonify({"msg": message}), 400

    admin_audit("job_status_update","job",job_id,f"from={old_status}; status={status}; reason={reason}")
    if status != old_status:
        message = f"Administrator «{job_title}» ishining holatini «{status}» ga o‘zgartirdi."
        if reason:
            message += f" Sabab: {reason}"
        for uid in {owner_id, worker_id} - {None}:
            create_notification(uid, "admin_job_update", "Ish holati o‘zgartirildi", message, "/jobs")
    return jsonify({"msg": "Ish holati o‘zgartirildi."})


@app.route("/admin/job/<int:job_id>", methods=["DELETE"])
@admin_required
def admin_delete_job(job_id):
    deletion_reason = str((request.get_json(silent=True) or {}).get("reason", "")).strip()
    if len(deletion_reason) > 1000:
        return jsonify({"msg": "O‘chirish sababi 1000 belgidan oshmasligi kerak."}), 400
    job = db.q("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi."}), 404

    held_payment = db.q("SELECT id FROM payments WHERE job_id=? AND status='held' LIMIT 1", (job_id,)).fetchone()
    if held_payment:
        return jsonify({"msg": "Bu ishda waiting to‘lovi bor. Avval refund qiling yoki shikoyatni admin orqali hal qiling."}), 409

    attachment_urls_to_remove = [
        row[0]
        for row in db.q("SELECT attachment_url FROM messages WHERE job_id=? AND attachment_url!=''", (job_id,)).fetchall()
        if row[0]
    ]
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM messages WHERE job_id=?", (job_id,))
        cur.execute("DELETE FROM ratings WHERE job_id=?", (job_id,))
        cur.execute("DELETE FROM job_proposals WHERE job_id=?", (job_id,))
        cur.execute("DELETE FROM favorites WHERE target_type='job' AND target_id=?", (job_id,))
        cur.execute("DELETE FROM reports WHERE job_id=?", (job_id,))
        cur.execute("DELETE FROM typing_states WHERE job_id=?", (job_id,))
        cur.execute("DELETE FROM job_services WHERE job_id=?", (job_id,))
        cur.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for attachment_url in attachment_urls_to_remove:
        _remove_stored_upload(attachment_url, "/uploads/chat/", CHAT_UPLOAD_DIR)

    admin_audit("job_delete","job",job_id,("Sabab: " + deletion_reason) if deletion_reason else "Admin jobni o‘chirdi.")
    return jsonify({"msg": "Ish o‘chirildi."})


@app.route("/admin/service", methods=["POST"])
@admin_required
def admin_create_service():
    d = request.json or {}
    name = str(d.get("name", "")).strip()
    parent_id = d.get("parent_id")

    if not name:
        return jsonify({"msg": "Xizmat nomi kiritilishi kerak."}), 400

    if parent_id in ("", None):
        parent_id = None
    else:
        try:
            parent_id = int(parent_id)
        except (TypeError, ValueError):
            return jsonify({"msg": "Ota kategoriya noto'g'ri."}), 400

        parent = db.q("SELECT id FROM services WHERE id=?", (parent_id,)).fetchone()
        if not parent:
            return jsonify({"msg": "Ota kategoriya topilmadi."}), 404

    duplicate = db.q(
        "SELECT id FROM services WHERE name=? AND parent_id IS ?",
        (name, parent_id)
    ).fetchone()
    if duplicate:
        return jsonify({"msg": "Bunday xizmat allaqachon mavjud."}), 409

    result = db.q(
        "INSERT INTO services(name,parent_id,created_by) VALUES(?,?,?)",
        (name, parent_id, request.uid)
    )
    new_id = result.lastrowid
    result.close()

    admin_audit("service_create","service",new_id,name)
    return jsonify({"msg": "Xizmat qo‘shildi.", "id": new_id}), 201


@app.route("/admin/service/<int:service_id>", methods=["PATCH"])
@admin_required
def admin_update_service(service_id):
    data = request.json or {}
    name = str(data.get("name", "")).strip()
    parent_raw = data.get("parent_id")
    if not name or len(name) > 120:
        return jsonify({"msg": "Xizmat nomi 1–120 belgidan iborat bo‘lishi kerak"}), 400
    service = db.q("SELECT id,name,parent_id FROM services WHERE id=?", (service_id,)).fetchone()
    if not service:
        return jsonify({"msg": "Xizmat topilmadi"}), 404
    if parent_raw in ("", None, "null"):
        parent_id = None
    else:
        try:
            parent_id = int(parent_raw)
        except (TypeError, ValueError):
            return jsonify({"msg": "Ota kategoriya noto‘g‘ri"}), 400
        if parent_id == service_id:
            return jsonify({"msg": "Xizmat o‘ziga ota kategoriya bo‘la olmaydi"}), 400
        parent = db.q("SELECT id FROM services WHERE id=?", (parent_id,)).fetchone()
        if not parent:
            return jsonify({"msg": "Ota kategoriya topilmadi"}), 404
        descendant = db.q(
            """WITH RECURSIVE descendants(id) AS (
                   SELECT id FROM services WHERE parent_id=?
                   UNION ALL
                   SELECT s.id FROM services s JOIN descendants d ON s.parent_id=d.id
               ) SELECT id FROM descendants WHERE id=? LIMIT 1""",
            (service_id, parent_id)
        ).fetchone()
        if descendant:
            return jsonify({"msg": "Xizmatni o‘zining ichidagi kategoriyaga ko‘chira olmaysiz"}), 400
    duplicate = db.q("SELECT id FROM services WHERE name=? AND parent_id IS ? AND id!=?",
                     (name, parent_id, service_id)).fetchone()
    if duplicate:
        return jsonify({"msg": "Bu ota kategoriya ichida bunday xizmat bor"}), 409
    db.q("UPDATE services SET name=?,parent_id=? WHERE id=?", (name, parent_id, service_id)).close()
    admin_audit("service_update", "service", service_id,
                f"name={name}; parent_id={parent_id}")
    return jsonify({"msg": "Xizmat yangilandi", "id": service_id, "name": name, "parent_id": parent_id})


@app.route("/admin/service/<int:service_id>", methods=["DELETE"])
@admin_required
def admin_delete_service(service_id):
    deletion_reason = str((request.get_json(silent=True) or {}).get("reason", "")).strip()
    if len(deletion_reason) > 1000:
        return jsonify({"msg": "O‘chirish sababi 1000 belgidan oshmasligi kerak."}), 400
    service = db.q("SELECT id FROM services WHERE id=?", (service_id,)).fetchone()
    if not service:
        return jsonify({"msg": "Xizmat topilmadi."}), 404

    child = db.q("SELECT id FROM services WHERE parent_id=? LIMIT 1", (service_id,)).fetchone()
    if child:
        return jsonify({"msg": "Avval uning ichidagi xizmatlarni o'chiring."}), 409

    used = db.q(
        "SELECT id FROM jobs WHERE service_id=? OR id IN (SELECT job_id FROM job_services WHERE service_id=?) LIMIT 1",
        (service_id, service_id)
    ).fetchone()
    if used:
        return jsonify({"msg": "Bu xizmat mavjud joblarda ishlatilgan, o'chirib bo'lmaydi."}), 409

    db.q("DELETE FROM services WHERE id=?", (service_id,)).close()
    admin_audit("service_delete","service",service_id,("Sabab: " + deletion_reason) if deletion_reason else "Admin xizmatni o‘chirdi.")
    return jsonify({"msg": "Xizmat o‘chirildi."})


@app.route("/admin/rating/<int:rating_id>", methods=["DELETE"])
@admin_required
def admin_delete_rating(rating_id):
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason", "")).strip()
    if len(reason) > 1000:
        return jsonify({"msg": "O‘chirish sababi 1000 belgidan oshmasligi kerak"}), 400
    rating = db.q("SELECT id FROM ratings WHERE id=?", (rating_id,)).fetchone()
    if not rating:
        return jsonify({"msg": "Baho topilmadi."}), 404

    target = db.q("SELECT to_user FROM ratings WHERE id=?", (rating_id,)).fetchone()
    db.q("DELETE FROM ratings WHERE id=?", (rating_id,)).close()

    if target:
        average = db.q(
            "SELECT COALESCE(AVG(score), 0) FROM ratings WHERE to_user=?",
            (target[0],)
        ).fetchone()[0]
        db.q("UPDATE users SET average_rating=? WHERE id=?", (round(float(average), 2), target[0])).close()

    admin_audit("rating_delete","rating",rating_id,("Sabab: " + reason) if reason else "Admin bahoni o‘chirdi.")
    return jsonify({"msg": "Baho o‘chirildi."})


# -------- AUTH --------
def issue_user_token(user_id):
    role_row = db.q("SELECT role, COALESCE(token_version,0) FROM users WHERE id=?", (user_id,)).fetchone()
    user_role = role_row[0] if role_row and role_row[0] else "user"
    token_version = int(role_row[1] if role_row else 0)
    return token(user_id, role=user_role, token_version=token_version), user_role


def verify_google_credential(credential):
    if not GOOGLE_CLIENT_ID:
        return None, "GOOGLE_CLIENT_ID serverda sozlanmagan."

    try:
        request_obj = URLRequest(
            "https://oauth2.googleapis.com/tokeninfo?" + urlencode({"id_token": credential}),
            headers={"Accept": "application/json"},
        )
        with urlopen(request_obj, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None, "Google credentialini tekshirib bo‘lmadi."

    if payload.get("aud") != GOOGLE_CLIENT_ID:
        return None, "Google credentiali ushbu FinJob ilovasiga tegishli emas."
    if payload.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        return None, "Google credentiali ishonchsiz."
    if str(payload.get("email_verified", "")).lower() != "true":
        return None, "Google email manzili tasdiqlanmagan."

    email = str(payload.get("email", "")).strip().lower()
    sub = str(payload.get("sub", "")).strip()
    if not email or not sub:
        return None, "Google account ma’lumotlari to‘liq emas."
    return payload, None


def make_google_username(email):
    base = re.sub(r"[^A-Za-z0-9_.-]", "", email.split("@", 1)[0])[:24] or "googleuser"
    username = base
    suffix = 1
    while db.q("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        suffix_text = str(suffix)
        username = (base[:32-len(suffix_text)-1] + "_" + suffix_text)
        suffix += 1
    return username


@app.route("/auth/google", methods=["POST"])
def google_auth():
    d = request.json or {}
    credential = str(d.get("credential", "")).strip()
    if not credential:
        return jsonify({"msg": "Google credentiali yuborilmadi."}), 400

    google_user, error = verify_google_credential(credential)
    if error:
        return jsonify({"msg": error}), 400

    email = google_user["email"].lower()
    google_sub = google_user["sub"]
    existing = db.q(
        "SELECT id, role, auth_provider, google_sub FROM users WHERE google_sub=? OR lower(email)=?",
        (google_sub, email),
    ).fetchone()

    if existing:
        if existing[3] != google_sub:
            return jsonify({"msg": "Bu email allaqachon parol orqali ro‘yxatdan o‘tgan. Avval shu accountga parol bilan kiring."}), 409
        access_token, user_role = issue_user_token(existing[0])
        return jsonify({"token": access_token, "role": user_role})

    first_name = str(google_user.get("given_name", "")).strip()[:100]
    last_name = str(google_user.get("family_name", "")).strip()[:100]
    username = make_google_username(email)
    picture = str(google_user.get("picture", "")).strip()[:1000]
    random_password = generate_password_hash(secrets.token_urlsafe(32))
    now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        db.q(
            """INSERT INTO users(
                username,password,first_name,last_name,birthday,email,bio,skills,
                created_at,average_rating,role,avatar_url,auth_provider,google_sub
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                username,
                random_password,
                first_name or username,
                last_name,
                "",
                email,
                "",
                "",
                now_time,
                0.0,
                "user",
                picture,
                "google",
                google_sub,
            ),
        )
        new_user = db.q("SELECT id FROM users WHERE google_sub=?", (google_sub,)).fetchone()
        access_token, user_role = issue_user_token(new_user[0])
        return jsonify({"token": access_token, "role": user_role})
    except sqlite3.IntegrityError:
        return jsonify({"msg": "Google accountni ro‘yxatdan o‘tkazishda account allaqachon mavjud bo‘lib qoldi. Qayta urinib ko‘ring."}), 409


@app.route("/login", methods=["POST"])
def login():
    d = request.json or {}
    username_or_email = str(d.get("username", "")).strip()
    login_email = username_or_email.lower()
    password = str(d.get("password", ""))

    if not username_or_email or not password:
        return jsonify({"msg": "Foydalanuvchi nomi/elektron pochta va parol kiritilishi shart!"}), 400
    if len(username_or_email) > 254:
        return jsonify({"msg": "Foydalanuvchi nomi yoki elektron pochta juda uzun"}), 400

    if len(password) < 8 or len(password) > 256:
        return jsonify({"msg": "Parol 8–256 belgidan iborat bo‘lishi kerak"}), 400

    u = db.q(
        "SELECT id, password, role, auth_provider FROM users WHERE username=? OR lower(email)=?",
        (username_or_email, login_email),
    ).fetchone()
    if u and u[1] and check_password_hash(u[1], password):
        user_role = u[2] if len(u) > 2 and u[2] else "user"
        version_row = db.q("SELECT COALESCE(token_version,0) FROM users WHERE id=?", (u[0],)).fetchone()
        token_version = int(version_row[0] if version_row else 0)
        return jsonify({"token": token(u[0], role=user_role, token_version=token_version), "role": user_role})
    return jsonify({"msg": "Foydalanuvchi nomi/elektron pochta yoki parol xato!"}), 401


# 1-QADAM: Emailga tasdiqlash kodini yuborish
@app.route("/register/send-code", methods=["POST"])
def send_code():
    d = request.json
    if not d:
        return jsonify({"msg": "Ma'lumotlar yuborilmadi"}), 400

    req = ["username", "password", "first_name", "last_name", "birthday", "email"]
    for i in req:
        if i not in d or not str(d[i]).strip():
            return jsonify({"msg": f"{i} maydoni to'ldirilishi shart"}), 400

    username = str(d["username"]).strip()
    email = str(d["email"]).strip().lower()
    password = str(d["password"])
    first_name = str(d["first_name"]).strip()
    last_name = str(d["last_name"]).strip()
    birthday = str(d["birthday"]).strip()

    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
        return jsonify({"msg": "Foydalanuvchi nomi 3–32 belgidan iborat bo‘lishi va faqat harf, raqam, _ . - belgilaridan foydalanishi kerak"}), 400

    if len(password) < 8 or len(password) > 256:
        return jsonify({"msg": "Parol 8–256 belgidan iborat bo‘lishi kerak"}), 400

    if len(first_name) > 100 or len(last_name) > 100 or len(birthday) > 32:
        return jsonify({"msg": "Ism, familiya yoki tug‘ilgan sana juda uzun"}), 400

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
        return jsonify({"msg": "Elektron pochta manzili noto‘g‘ri"}), 400

    exists_u = db.q("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if exists_u:
        return jsonify({"msg": "Ushbu foydalanuvchi nomi allaqachon band!"}), 400

    exists_e = db.q("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if exists_e:
        return jsonify({"msg": "Ushbu elektron pochta allaqachon ro‘yxatdan o‘tgan!"}), 400

    code = str(secrets.randbelow(900000) + 100000)
    email_key = email
    now_dt = datetime.datetime.now()
    expired_keys = [key for key, value in pending_verifications.items() if now_dt > value.get("expiry", now_dt)]
    for key in expired_keys:
        pending_verifications.pop(key, None)
    if email_key not in pending_verifications and len(pending_verifications) >= 5000:
        return jsonify({"msg": "Tasdiqlash xizmatida vaqtinchalik yuklama yuqori. Keyinroq qayta urinib ko‘ring."}), 503

    pending_verifications[email_key] = {
        "code": code,
        "attempts": 0,
        "data": {**d, "email": email_key, "username": username, "password": generate_password_hash(password)},
        "expiry": datetime.datetime.now() + datetime.timedelta(minutes=10),
    }

    if not send_email_code(email_key, code):
        pending_verifications.pop(email_key, None)
        return jsonify({"msg": "Tasdiqlash xatini yuborib bo‘lmadi. Elektron pochta sozlamalarini tekshiring."}), 502
    return jsonify({"msg": "ok", "info": "Tasdiqlash kodi elektron pochtangizga yuborildi."})


# 2-QADAM: Kodni tasdiqlab ro'yxatdan o'tkazish
@app.route("/register/verify", methods=["POST"])
def verify_code():
    d = request.json
    if not d or "email" not in d or "code" not in d:
        return jsonify({"msg": "Elektron pochta va tasdiqlash kodi talab qilinadi"}), 400

    email = str(d["email"]).strip().lower()
    code = str(d["code"]).strip()

    if email not in pending_verifications:
        return jsonify({"msg": "Ushbu elektron pochta uchun tasdiqlash kodi so‘ralmagan yoki eskirgan!"}), 400

    record = pending_verifications[email]

    if datetime.datetime.now() > record["expiry"]:
        del pending_verifications[email]
        return jsonify({"msg": "Tasdiqlash kodining amal qilish muddati tugagan. Qaytadan so'rang."}), 400

    if not code.isdigit() or len(code) != 6:
        record["attempts"] += 1
        if record["attempts"] >= 5:
            del pending_verifications[email]
            return jsonify({"msg": "Tasdiqlash kodi uchun urinishlar limiti tugadi. Yangi kod so‘rang."}), 429
        return jsonify({"msg": "Tasdiqlash kodi noto'g'ri!"}), 400

    record["attempts"] += 1
    if not secrets.compare_digest(record["code"], code):
        if record["attempts"] >= 5:
            del pending_verifications[email]
            return jsonify({"msg": "Tasdiqlash kodi uchun urinishlar limiti tugadi. Yangi kod so‘rang."}), 429
        return jsonify({"msg": "Tasdiqlash kodi noto'g'ri!"}), 400

    ud = record["data"]
    try:
        now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        assigned_role = "user"

        db.q(
            """INSERT INTO users(username,password,first_name,last_name,birthday,email,bio,skills,created_at,average_rating,role,auth_provider)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ud["username"],
                ud["password"],
                ud["first_name"],
                ud["last_name"],
                ud["birthday"],
                ud["email"],
                "",
                "",
                now_time,
                0.0,
                assigned_role,
                "password",
            ),
        )

        del pending_verifications[email]
        return jsonify({"msg": "ok", "role": assigned_role})
    except Exception:
        return jsonify({"msg": "Ro'yxatdan o'tishda xatolik yuz berdi"}), 400


@app.route("/forgot-password/send-code", methods=["POST"])
def forgot_password_send_code():
    d = request.json or {}
    email = str(d.get("email", "")).strip().lower()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
        return jsonify({"msg": "Elektron pochta manzili noto‘g‘ri."}), 400

    # Har doim bir xil javob qaytaramiz: email accountga tegishli ekanini oshkor qilmaymiz.
    user = db.q("SELECT id FROM users WHERE lower(email)=?", (email,)).fetchone()
    if not user:
        return jsonify({"msg": "Agar bu email FinJob accountiga tegishli bo‘lsa, tiklash kodi yuborildi."})

    code = str(secrets.randbelow(900000) + 100000)
    now_dt = datetime.datetime.now()
    expired_keys = [key for key, value in pending_password_resets.items() if now_dt > value.get("expiry", now_dt)]
    for key in expired_keys:
        pending_password_resets.pop(key, None)

    pending_password_resets[email] = {
        "code": code,
        "attempts": 0,
        "user_id": int(user[0]),
        "expiry": now_dt + datetime.timedelta(minutes=10),
    }

    if not send_auth_code_email(email, code, "reset"):
        pending_password_resets.pop(email, None)
        return jsonify({"msg": "Email yuborilmadi. Keyinroq qayta urinib ko‘ring."}), 502

    return jsonify({"msg": "Agar bu email FinJob accountiga tegishli bo‘lsa, tiklash kodi yuborildi."})


@app.route("/forgot-password/reset", methods=["POST"])
def forgot_password_reset():
    d = request.json or {}
    email = str(d.get("email", "")).strip().lower()
    code = str(d.get("code", "")).strip()
    new_password = str(d.get("password", ""))

    if not email or not code or len(code) != 6 or not code.isdigit():
        return jsonify({"msg": "Email va 6 xonali kodni to‘g‘ri kiriting."}), 400
    if len(new_password) < 8 or len(new_password) > 256:
        return jsonify({"msg": "Yangi parol 8–256 belgidan iborat bo‘lishi kerak."}), 400

    record = pending_password_resets.get(email)
    if not record:
        return jsonify({"msg": "Kod topilmadi yoki uning muddati tugagan. Yangi kod so‘rang."}), 400

    if datetime.datetime.now() > record["expiry"]:
        pending_password_resets.pop(email, None)
        return jsonify({"msg": "Kodning amal qilish muddati tugagan. Yangi kod so‘rang."}), 400

    record["attempts"] += 1
    if not secrets.compare_digest(record["code"], code):
        if record["attempts"] >= 5:
            pending_password_resets.pop(email, None)
            return jsonify({"msg": "Kod uchun urinishlar limiti tugadi. Yangi kod so‘rang."}), 429
        return jsonify({"msg": "Tasdiqlash kodi noto‘g‘ri."}), 400

    password_hash = generate_password_hash(new_password)
    db.q(
        "UPDATE users SET password=?, token_version=COALESCE(token_version,0)+1 WHERE id=?",
        (password_hash, record["user_id"]),
    ).close()
    pending_password_resets.pop(email, None)
    return jsonify({"msg": "ok"})


@app.route("/logout", methods=["POST"])
@auth
def logout():
    db.q("UPDATE users SET token_version=COALESCE(token_version,0)+1 WHERE id=?", (request.uid,)).close()
    return jsonify({"msg": "ok"})


# -------- SERVICES (ADMIN AUTHORIZATION REQUIRED) --------
@app.route("/services")
def get_services():
    r = db.q("SELECT id,name,parent_id FROM services").fetchall()
    return jsonify(rows(r, ["id", "name", "parent_id"]))


@app.route("/saved-searches", methods=["GET", "POST"])
@auth
def saved_searches():
    if request.method == "GET":
        items = db.q(
            "SELECT id,name,filters,created_at,updated_at FROM saved_searches WHERE user_id=? ORDER BY updated_at DESC,id DESC LIMIT 50",
            (request.uid,),
        ).fetchall()
        result = []
        for item in items:
            try:
                filters = json.loads(item[2] or "{}")
            except (TypeError, ValueError):
                filters = {}
            result.append({"id": item[0], "name": item[1], "filters": filters, "created_at": item[3], "updated_at": item[4]})
        return jsonify(result)

    data = request.json or {}
    name = str(data.get("name", "")).strip()
    filters = data.get("filters") if isinstance(data.get("filters"), dict) else {}
    if not name or len(name) > 80:
        return jsonify({"msg": "Saqlangan qidiruv nomi 1–80 belgidan iborat bo‘lishi kerak"}), 400
    allowed = {"search", "service_ids", "min_price", "max_price", "time_filter", "location"}
    filters = {key: filters.get(key) for key in allowed if filters.get(key) not in ("", None, [], "all")}
    if "service_ids" in filters and not isinstance(filters["service_ids"], list):
        return jsonify({"msg": "Xizmat filtri noto‘g‘ri"}), 400
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    serialized = json.dumps(filters, ensure_ascii=False, separators=(",", ":"))
    existing = db.q("SELECT id FROM saved_searches WHERE user_id=? AND name=?", (request.uid, name)).fetchone()
    if existing:
        db.q("UPDATE saved_searches SET filters=?,updated_at=? WHERE id=? AND user_id=?", (serialized, now, existing[0], request.uid)).close()
        return jsonify({"msg": "ok", "id": existing[0], "updated": True})
    count = db.q("SELECT COUNT(*) FROM saved_searches WHERE user_id=?", (request.uid,)).fetchone()[0]
    if int(count) >= 20:
        return jsonify({"msg": "Ko‘pi bilan 20 ta saqlangan qidiruv bo‘lishi mumkin"}), 400
    result = db.q("INSERT INTO saved_searches(user_id,name,filters,created_at,updated_at) VALUES(?,?,?,?,?)", (request.uid, name, serialized, now, now))
    saved_id = result.lastrowid
    result.close()
    return jsonify({"msg": "ok", "id": saved_id, "created": True}), 201


@app.route("/saved-searches/<int:search_id>", methods=["DELETE"])
@auth
def delete_saved_search(search_id):
    result = db.q("DELETE FROM saved_searches WHERE id=? AND user_id=?", (search_id, request.uid))
    deleted = result.rowcount
    result.close()
    if deleted != 1:
        return jsonify({"msg": "Saqlangan qidiruv topilmadi"}), 404
    return jsonify({"msg": "ok"})


@app.route("/recently-viewed", methods=["GET"])
@auth
def get_recently_viewed():
    items = db.q(
        """SELECT rv.job_id,rv.viewed_at,j.title,COALESCE(j.agreed_price,j.price),j.currency,j.location,j.status,
                  j.user_id,j.worker_id,j.created_at
           FROM recently_viewed rv
           JOIN jobs j ON j.id=rv.job_id
           WHERE rv.user_id=? AND j.status!='blocked'
             AND (j.status='active' OR j.user_id=? OR j.worker_id=?)
           ORDER BY rv.viewed_at DESC,rv.id DESC LIMIT 20""",
        (request.uid, request.uid, request.uid),
    ).fetchall()
    return jsonify([
        {"job_id": x[0], "viewed_at": x[1], "title": x[2], "price": x[3], "currency": x[4], "location": x[5],
         "status": x[6], "user_id": x[7], "worker_id": x[8], "created_at": x[9]}
        for x in items
    ])


@app.route("/recently-viewed/<int:job_id>", methods=["POST"])
@auth
def add_recently_viewed(job_id):
    job = db.q("SELECT id FROM jobs WHERE id=? AND status!='blocked' AND (status='active' OR user_id=? OR worker_id=?)", (job_id, request.uid, request.uid)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi"}), 404
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.q("DELETE FROM recently_viewed WHERE user_id=? AND job_id=?", (request.uid, job_id)).close()
    db.q("INSERT INTO recently_viewed(user_id,job_id,viewed_at) VALUES(?,?,?)", (request.uid, job_id, now)).close()
    return jsonify({"msg": "ok"})


# -------- REVERSE GEOCODING --------
@app.route("/reverse-geocode")
@auth
def reverse_geocode():
    try:
        latitude = float(request.args.get("lat", ""))
        longitude = float(request.args.get("lon", ""))
    except (TypeError, ValueError):
        return jsonify({"msg": "Joylashuv koordinatalari noto'g'ri"}), 400

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({"msg": "Joylashuv koordinatalari noto'g'ri"}), 400

    query = urlencode({
        "format": "jsonv2",
        "lat": latitude,
        "lon": longitude,
        "zoom": 18,
        "addressdetails": 1,
        "accept-language": "uz,ru,en",
    })
    geocoder_url = f"https://nominatim.openstreetmap.org/reverse?{query}"

    try:
        geocoder_request = URLRequest(
            geocoder_url,
            headers={
                "User-Agent": "FinJob/1.0 (+https://github.com/XudayberganovAllanazar1211/Job-Application-Loyiha)",
                "Accept": "application/json",
            },
        )
        with urlopen(geocoder_request, timeout=6) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        return jsonify({"msg": "Joylashuv manzilini aniqlab bo'lmadi"}), 502

    location = str(data.get("display_name", "")).strip()
    if not location:
        return jsonify({"msg": "Bu joy uchun manzil topilmadi"}), 404

    return jsonify({
        "msg": "ok",
        "location": location,
        "latitude": latitude,
        "longitude": longitude,
    })


# -------- JOBS --------
@app.route("/job", methods=["POST"])
@auth
def add_job():
    block_response=enforce_block("job_creation")
    if block_response: return block_response

    
    d = request.json or {}

    title = str(d.get("title", "")).strip()
    description = str(d.get("description", "")).strip()
    location = str(d.get("location", "")).strip()
    currency = str(d.get("currency", "UZS")).strip().upper()

    raw_service_ids = d.get("service_ids") or []
    if not isinstance(raw_service_ids, list):
        raw_service_ids = [raw_service_ids]

    if not raw_service_ids and d.get("service_id"):
        raw_service_ids = [d.get("service_id")]

    if len(raw_service_ids) > 20:
        return jsonify({"msg": "Bir ishda ko‘pi bilan 20 ta xizmat tanlash mumkin"}), 400

    valid_service_ids = []
    seen_service_ids = set()

    for raw_service_id in raw_service_ids:
        try:
            service_id = int(raw_service_id)
        except (TypeError, ValueError):
            continue

        if service_id in seen_service_ids:
            continue

        service = db.q("SELECT id FROM services WHERE id=?", (service_id,)).fetchone()
        if service:
            seen_service_ids.add(service_id)
            valid_service_ids.append(service_id)

    raw_custom_services = d.get("custom_services")
    if isinstance(raw_custom_services, list):
        custom_service_values = raw_custom_services
    else:
        custom_service_values = str(d.get("custom_service", "")).split(",")

    if len(custom_service_values) > 20:
        return jsonify({"msg": "Bir ishda ko‘pi bilan 20 ta yangi xizmat nomi bo‘lishi mumkin"}), 400

    custom_services = []
    seen_custom_services = set()

    for item in custom_service_values:
        custom_service = str(item).strip()
        if len(custom_service) > 120:
            return jsonify({"msg": "Xizmat nomi 120 belgidan oshmasligi kerak"}), 400
        key = custom_service.casefold()
        if custom_service and key not in seen_custom_services:
            seen_custom_services.add(key)
            custom_services.append(custom_service)

    if not title or not location:
        return jsonify({"msg": "Sarlavha va manzil maydonlarini to‘ldiring"}), 400

    if len(title) > 160:
        return jsonify({"msg": "Sarlavha 160 belgidan oshmasligi kerak"}), 400

    if len(description) > 5000:
        return jsonify({"msg": "Tavsif 5000 belgidan oshmasligi kerak"}), 400

    if len(location) > 300:
        return jsonify({"msg": "Manzil 300 belgidan oshmasligi kerak"}), 400

    if not valid_service_ids and not custom_services:
        return jsonify({"msg": "Kamida bitta xizmat tanlang yoki yangi xizmat nomini kiriting"}), 400

    if not d.get("price"):
        return jsonify({"msg": "Narx kiritilishi shart"}), 400

    try:
        price = float(d["price"])
    except (TypeError, ValueError):
        return jsonify({"msg": "Narx noto'g'ri kiritilgan"}), 400

    if not math.isfinite(price) or price <= 0 or price > 100000000000:
        return jsonify({"msg": "Narx 0 dan katta va 100 000 000 000 dan oshmasligi kerak"}), 400

    if currency != "UZS":
        return jsonify({"msg": "Hozircha FinJob to‘lovlari faqat UZS valyutasida ishlaydi"}), 400

    primary_service_id = valid_service_ids[0] if valid_service_ids else None
    custom_service_text = ", ".join(custom_services)
    now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    insert_result = db.q(
        """INSERT INTO jobs(user_id,service_id,custom_service,title,description,price,location,worker_id,status,created_at,currency,agreed_price)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            request.uid,
            primary_service_id,
            custom_service_text,
            title,
            description,
            price,
            location,
            None,
            "active",
            now_time,
            currency,
            None,
        ),
    )
    job_id = insert_result.lastrowid
    insert_result.close()

    for service_id in valid_service_ids:
        result = db.q(
            "INSERT INTO job_services(job_id,service_id,custom_service) VALUES(?,?,?)",
            (job_id, service_id, ""),
        )
        result.close()

    for custom_service in custom_services:
        result = db.q(
            "INSERT INTO job_services(job_id,service_id,custom_service) VALUES(?,?,?)",
            (job_id, None, custom_service),
        )
        result.close()

    notify_matching_users(job_id, title, request.uid)
    return jsonify({"msg": "ok"})


@app.route("/jobs")
@auth
def get_jobs():
    block_response = enforce_block("full")
    if block_response:
        return block_response

    def parse_positive_int(value, default, maximum):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(1, min(maximum, parsed))

    def parse_service_ids(raw):
        values = []
        for item in str(raw or "").split(","):
            try:
                value = int(item)
            except (TypeError, ValueError):
                continue
            if value > 0 and value not in values:
                values.append(value)
        return values[:20]

    search = str(request.args.get("search", request.args.get("q", ""))).strip()
    location = str(request.args.get("location", "")).strip()
    time_filter = str(request.args.get("time", request.args.get("time_filter", "all"))).strip().lower()
    service_ids = parse_service_ids(request.args.get("service_ids", request.args.get("service_id", "")))
    saved_only = str(request.args.get("saved_only", "0")).strip().lower() in {"1", "true", "yes", "on"}

    min_price = None
    max_price = None
    try:
        if str(request.args.get("min_price", "")).strip() != "":
            min_price = float(request.args.get("min_price"))
        if str(request.args.get("max_price", "")).strip() != "":
            max_price = float(request.args.get("max_price"))
    except (TypeError, ValueError):
        return jsonify({"msg": "Narx filtri noto‘g‘ri kiritilgan"}), 400

    if min_price is not None and (not math.isfinite(min_price) or min_price < 0):
        return jsonify({"msg": "Minimal narx noto‘g‘ri"}), 400
    if max_price is not None and (not math.isfinite(max_price) or max_price < 0):
        return jsonify({"msg": "Maksimal narx noto‘g‘ri"}), 400
    if min_price is not None and max_price is not None and min_price > max_price:
        return jsonify({"msg": "Minimal narx maksimal narxdan katta bo‘lishi mumkin emas"}), 400

    time_days = {"all": None, "today": 1, "three_days": 3, "week": 7, "month": 30}.get(time_filter)
    if time_days is None and time_filter != "all":
        return jsonify({"msg": "Vaqt filtri noto‘g‘ri"}), 400

    conditions = [
        """(
            j.status = 'active'
            OR (
                j.status IN ('payment_pending', 'accepted', 'pending_finish', 'finished')
                AND (j.user_id = ? OR j.worker_id = ?)
            )
        )"""
    ]
    args = [request.uid, request.uid]

    if search:
        like = f"%{search}%"
        conditions.append(
            """(
                j.title LIKE ? COLLATE NOCASE
                OR j.description LIKE ? COLLATE NOCASE
                OR j.location LIKE ? COLLATE NOCASE
                OR j.custom_service LIKE ? COLLATE NOCASE
                OR EXISTS (
                    SELECT 1
                    FROM job_services js_search
                    JOIN services s_search ON s_search.id = js_search.service_id
                    WHERE js_search.job_id = j.id AND s_search.name LIKE ? COLLATE NOCASE
                )
            )"""
        )
        args.extend([like, like, like, like, like])

    if location:
        conditions.append("j.location LIKE ? COLLATE NOCASE")
        args.append(f"%{location}%")

    if min_price is not None:
        conditions.append("COALESCE(j.agreed_price, j.price) >= ?")
        args.append(min_price)

    if max_price is not None:
        conditions.append("COALESCE(j.agreed_price, j.price) <= ?")
        args.append(max_price)

    if time_days is not None:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=time_days)).strftime("%Y-%m-%d %H:%M:%S")
        conditions.append("j.created_at >= ?")
        args.append(cutoff)

    if service_ids:
        placeholders = ",".join("?" for _ in service_ids)
        conditions.append(
            f"""(
                j.service_id IN (
                    WITH RECURSIVE service_tree(id) AS (
                        SELECT id FROM services WHERE id IN ({placeholders})
                        UNION ALL
                        SELECT s_child.id
                        FROM services s_child
                        JOIN service_tree st ON s_child.parent_id = st.id
                    )
                    SELECT id FROM service_tree
                )
                OR EXISTS (
                    SELECT 1
                    FROM job_services js_filter
                    WHERE js_filter.job_id = j.id
                      AND js_filter.service_id IN (
                          WITH RECURSIVE service_tree2(id) AS (
                              SELECT id FROM services WHERE id IN ({placeholders})
                              UNION ALL
                              SELECT s_child2.id
                              FROM services s_child2
                              JOIN service_tree2 st2 ON s_child2.parent_id = st2.id
                          )
                          SELECT id FROM service_tree2
                      )
                )
            )"""
        )
        args.extend(service_ids)
        args.extend(service_ids)

    if saved_only:
        conditions.append(
            "EXISTS (SELECT 1 FROM favorites f_saved WHERE f_saved.user_id=? AND f_saved.target_type='job' AND f_saved.target_id=j.id)"
        )
        args.append(request.uid)

    where_sql = " AND ".join(conditions)
    select_sql = f"""
        SELECT j.id, j.title, COALESCE(j.agreed_price, j.price) as price, j.currency, j.location, j.status, j.user_id, j.worker_id,
               w.first_name, w.last_name, w.username,
               j.description, j.service_id,
               (SELECT COUNT(*) FROM job_proposals jp WHERE jp.job_id=j.id AND jp.status='pending') as proposal_count,
               COALESCE(
                   (SELECT GROUP_CONCAT(
                       CASE WHEN js.service_id IS NOT NULL THEN ss.name ELSE js.custom_service END,
                       ', '
                   )
                    FROM job_services js
                    LEFT JOIN services ss ON js.service_id = ss.id
                    WHERE js.job_id = j.id),
                   COALESCE(NULLIF(s.name, ''), j.custom_service)
               ) as service_name,
               j.created_at, j.owner_finished, j.worker_finished,
               c.first_name as creator_first, c.last_name as creator_last, c.username as creator_username
        FROM jobs j
        LEFT JOIN users w ON j.worker_id = w.id
        LEFT JOIN users c ON j.user_id = c.id
        LEFT JOIN services s ON j.service_id = s.id
        WHERE {where_sql}
        ORDER BY j.id DESC
    """

    wants_pagination = any(
        key in request.args for key in
        ("page", "page_size", "search", "q", "location", "min_price", "max_price", "time", "time_filter", "service_ids", "service_id", "saved_only")
    )
    if not wants_pagination:
        r = db.q(select_sql, tuple(args)).fetchall()
        return jsonify(rows(r, [
            "id", "title", "price", "currency", "location", "status", "user_id", "worker_id",
            "worker_first", "worker_last", "worker_username", "description", "service_id",
            "proposal_count", "service_name", "created_at", "owner_finished", "worker_finished",
            "creator_first", "creator_last", "creator_username"
        ]))

    page = parse_positive_int(request.args.get("page"), 1, 1000000)
    page_size = parse_positive_int(request.args.get("page_size"), 10, 50)
    count = db.q(f"SELECT COUNT(*) FROM jobs j WHERE {where_sql}", tuple(args)).fetchone()[0]
    total_pages = max(1, math.ceil(int(count) / page_size))
    if page > total_pages:
        page = total_pages

    r = db.q(select_sql + " LIMIT ? OFFSET ?", tuple(args + [page_size, (page - 1) * page_size])).fetchall()
    items = rows(r, [
        "id", "title", "price", "currency", "location", "status", "user_id", "worker_id",
        "worker_first", "worker_last", "worker_username", "description", "service_id",
        "proposal_count", "service_name", "created_at", "owner_finished", "worker_finished",
        "creator_first", "creator_last", "creator_username"
    ])
    return jsonify({
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": int(count),
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1
        }
    })

@app.route("/jobs/<int:job_id>")
@auth
def get_job_detail(job_id):
    r = db.q(
        """
        SELECT j.id, j.title, COALESCE(j.agreed_price, j.price) as price, j.currency, j.location, j.status, j.user_id, j.worker_id,
               u.first_name, u.last_name, u.username, j.description, j.service_id,
               (SELECT COUNT(*) FROM job_proposals jp WHERE jp.job_id=j.id AND jp.status='pending') as proposal_count,
               COALESCE(
                   (SELECT GROUP_CONCAT(
                       CASE WHEN js.service_id IS NOT NULL THEN ss.name ELSE js.custom_service END,
                       ', '
                   )
                    FROM job_services js
                    LEFT JOIN services ss ON js.service_id = ss.id
                    WHERE js.job_id = j.id),
                   COALESCE(NULLIF(s.name, ''), j.custom_service)
               ) as service_name,
               j.created_at,
               j.owner_finished, j.worker_finished,
               c.first_name as creator_first, c.last_name as creator_last, c.username as creator_username
        FROM jobs j
        LEFT JOIN users u ON j.worker_id = u.id
        LEFT JOIN users c ON j.user_id = c.id
        LEFT JOIN services s ON j.service_id = s.id
        WHERE j.id = ?
          AND j.status != 'blocked' AND (j.status = 'active' OR j.user_id = ? OR j.worker_id = ?)
    """,
        (job_id, request.uid, request.uid),
    ).fetchone()

    if not r:
        return jsonify({"msg": "Ish topilmadi"}), 404

    return jsonify({
        "id": r[0],
        "title": r[1],
        "price": r[2],
        "currency": r[3],
        "location": r[4],
        "status": r[5],
        "user_id": r[6],
        "worker_id": r[7],
        "worker_first": r[8],
        "worker_last": r[9],
        "worker_username": r[10],
        "description": r[11],
        "service_id": r[12],
        "proposal_count": r[13],
        "service_name": r[14],
        "created_at": r[15],
        "owner_finished": r[16],
        "worker_finished": r[17],
        "creator_first": r[18],
        "creator_last": r[19],
        "creator_username": r[20],
    })



@app.route("/jobs/<int:job_id>/proposals", methods=["GET", "POST"])
@auth
def job_proposals(job_id):
    block_response=enforce_block("full") if request.method=="GET" else enforce_block("proposal")
    if block_response: return block_response

    
    job = db.q(
        "SELECT user_id, worker_id, status, price, title FROM jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi"}), 404

    owner_id, assigned_worker_id, job_status, job_price, job_title = job

    if request.method == "GET":
        if request.uid == owner_id:
            items = db.q(
                """SELECT p.id,p.job_id,p.worker_id,p.price,p.deadline,p.message,p.status,p.created_at,p.updated_at,
                          u.username,u.first_name,u.last_name,u.average_rating
                   FROM job_proposals p
                   JOIN users u ON u.id=p.worker_id
                   WHERE p.job_id=?
                   ORDER BY CASE WHEN p.status='pending' THEN 0 ELSE 1 END, p.created_at DESC""",
                (job_id,),
            ).fetchall()
        elif job_status == "active" or request.uid == assigned_worker_id:
            items = db.q(
                """SELECT p.id,p.job_id,p.worker_id,p.price,p.deadline,p.message,p.status,p.created_at,p.updated_at,
                          u.username,u.first_name,u.last_name,u.average_rating
                   FROM job_proposals p
                   JOIN users u ON u.id=p.worker_id
                   WHERE p.job_id=? AND p.worker_id=?
                   ORDER BY p.created_at DESC""",
                (job_id, request.uid),
            ).fetchall()
        else:
            return jsonify({"msg": "Ruxsat berilmadi"}), 403

        return jsonify([
            {
                "id": x[0], "job_id": x[1], "worker_id": x[2], "price": float(x[3]),
                "deadline": x[4], "message": x[5], "status": x[6],
                "created_at": x[7], "updated_at": x[8], "username": x[9],
                "first_name": x[10] or "", "last_name": x[11] or "",
                "average_rating": float(x[12] or 0),
            }
            for x in items
        ])

    if request.uid == owner_id:
        return jsonify({"msg": "Ish egasi o‘zi uchun taklif yubora olmaydi"}), 400
    if job_status != "active" or assigned_worker_id is not None:
        return jsonify({"msg": "Bu ish hozir takliflar uchun ochiq emas"}), 409

    data = request.json or {}
    try:
        proposal_price = float(data.get("price"))
    except (TypeError, ValueError):
        return jsonify({"msg": "Taklif narxi noto‘g‘ri"}), 400
    if not math.isfinite(proposal_price) or proposal_price <= 0 or proposal_price > 100000000000:
        return jsonify({"msg": "Taklif narxi 0 dan katta va 100 000 000 000 dan oshmasligi kerak"}), 400

    deadline = str(data.get("deadline", "")).strip()
    message = str(data.get("message", "")).strip()
    if not deadline or len(deadline) > 64:
        return jsonify({"msg": "Muddatni kiriting"}), 400
    if len(message) > 3000:
        return jsonify({"msg": "Taklif izohi 3000 belgidan oshmasligi kerak"}), 400

    existing = db.q(
        "SELECT id,status FROM job_proposals WHERE job_id=? AND worker_id=?",
        (job_id, request.uid),
    ).fetchone()
    now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if existing and existing[1] in ("accepted", "pending"):
        return jsonify({"msg": "Bu ish uchun faol taklifingiz allaqachon mavjud"}), 409

    if existing:
        result = db.q(
            """UPDATE job_proposals
               SET price=?,deadline=?,message=?,status='pending',updated_at=?
               WHERE id=?""",
            (proposal_price, deadline, message, now_time, existing[0]),
        )
    else:
        try:
            result = db.q(
                """INSERT INTO job_proposals(job_id,worker_id,price,deadline,message,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (job_id, request.uid, proposal_price, deadline, message, "pending", now_time, now_time),
            )
        except sqlite3.IntegrityError:
            return jsonify({"msg": "Bu ish uchun taklifingiz allaqachon mavjud"}), 409
    proposal_id = result.lastrowid
    result.close()

    create_notification(
        owner_id,
        "new_proposal",
        "Yangi ish taklifi",
        f"«{job_title}» ishiga {proposal_price:,.0f} UZS taklif olindi.",
        "/jobs",
    )
    return jsonify({"msg": "Taklif yuborildi.", "proposal_id": proposal_id}), 201


@app.route("/proposals/<int:proposal_id>", methods=["PATCH", "DELETE"])
@auth
def update_proposal(proposal_id):
    proposal = db.q(
        """SELECT p.id,p.job_id,p.worker_id,p.price,j.user_id,j.worker_id,j.status,j.title
           FROM job_proposals p JOIN jobs j ON j.id=p.job_id WHERE p.id=?""",
        (proposal_id,),
    ).fetchone()
    if not proposal:
        return jsonify({"msg": "Taklif topilmadi"}), 404

    _, job_id, proposal_worker_id, proposal_price, owner_id, assigned_worker_id, job_status, job_title = proposal
    action = "withdraw" if request.method == "DELETE" else str((request.json or {}).get("action", "")).strip().lower()

    if action == "withdraw":
        if request.uid != proposal_worker_id:
            return jsonify({"msg": "Faqat taklif egasi uni bekor qilishi mumkin"}), 403
        if job_status != "active":
            return jsonify({"msg": "Bu taklifni hozir bekor qilib bo‘lmaydi"}), 409
        db.q(
            "UPDATE job_proposals SET status='withdrawn',updated_at=? WHERE id=? AND status='pending'",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), proposal_id),
        ).close()
        return jsonify({"msg": "Taklif bekor qilindi."})

    if action == "edit":
        block_response = enforce_block("proposal")
        if block_response:
            return block_response
        if request.uid != proposal_worker_id:
            return jsonify({"msg": "Faqat taklif egasi uni tahrirlashi mumkin"}), 403
        if job_status != "active" or assigned_worker_id is not None:
            return jsonify({"msg": "Bu taklifni hozir tahrirlab bo‘lmaydi"}), 409

        proposal_data = request.json or {}
        try:
            edited_price = float(proposal_data.get("price"))
        except (TypeError, ValueError):
            return jsonify({"msg": "Taklif narxi noto‘g‘ri"}), 400
        if not math.isfinite(edited_price) or edited_price <= 0 or edited_price > 100000000000:
            return jsonify({"msg": "Taklif narxi 0 dan katta va 100 000 000 000 dan oshmasligi kerak"}), 400

        edited_deadline = str(proposal_data.get("deadline", "")).strip()
        edited_message = str(proposal_data.get("message", "")).strip()
        if not edited_deadline or len(edited_deadline) > 64:
            return jsonify({"msg": "Muddatni kiriting"}), 400
        if len(edited_message) > 3000:
            return jsonify({"msg": "Taklif izohi 3000 belgidan oshmasligi kerak"}), 400

        now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result = db.q(
            """UPDATE job_proposals
               SET price=?,deadline=?,message=?,updated_at=?
               WHERE id=? AND worker_id=? AND status='pending'""",
            (edited_price, edited_deadline, edited_message, now_time, proposal_id, request.uid),
        )
        updated = result.rowcount
        result.close()
        if updated != 1:
            return jsonify({"msg": "Bu taklif endi tahrirlash uchun faol emas"}), 409

        create_notification(
            owner_id,
            "proposal_updated",
            "Taklif yangilandi",
            f"«{job_title}» ishiga yuborilgan taklif yangilandi: {edited_price:,.0f} UZS.",
            "/jobs",
        )
        return jsonify({"msg": "Taklif yangilandi.", "proposal_id": proposal_id})

    if request.uid != owner_id:
        return jsonify({"msg": "Faqat ish egasi taklifni boshqarishi mumkin"}), 403
    if action not in ("accept", "reject"):
        return jsonify({"msg": "Amal noto‘g‘ri"}), 400

    if action == "reject":
        result = db.q(
            "UPDATE job_proposals SET status='rejected',updated_at=? WHERE id=? AND status='pending'",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), proposal_id),
        )
        if result.rowcount != 1:
            result.close()
            return jsonify({"msg": "Bu taklif endi faol emas"}), 409
        result.close()
        create_notification(
            proposal_worker_id,
            "proposal_rejected",
            "Taklifingiz rad etildi",
            f"«{job_title}» ishiga yuborgan taklifingiz rad etildi.",
            "/jobs",
        )
        return jsonify({"msg": "Taklif rad etildi."})

    if job_status != "active" or assigned_worker_id is not None:
        return jsonify({"msg": "Bu ish uchun boshqa bajaruvchi allaqachon biriktirilgan"}), 409

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        pending = cur.execute(
            "SELECT status FROM job_proposals WHERE id=?",
            (proposal_id,),
        ).fetchone()
        if not pending or pending[0] != "pending":
            conn.rollback()
            return jsonify({"msg": "Bu taklif endi faol emas"}), 409

        cur.execute(
            """UPDATE jobs
               SET worker_id=?,status='payment_pending',agreed_price=?,
                   finished_at=NULL,owner_finished=0,worker_finished=0
               WHERE id=? AND status='active' AND worker_id IS NULL""",
            (proposal_worker_id, float(proposal_price), job_id),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return jsonify({"msg": "Ishni biriktirishda to‘qnashuv yuz berdi"}), 409

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE job_proposals SET status='accepted',updated_at=? WHERE id=?", (now, proposal_id))
        cur.execute(
            "UPDATE job_proposals SET status='rejected',updated_at=? WHERE job_id=? AND id!=? AND status='pending'",
            (now, job_id, proposal_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        return jsonify({"msg": "Taklifni qabul qilishda xatolik yuz berdi"}), 500
    finally:
        conn.close()

    create_notification(
        proposal_worker_id,
        "proposal_accepted",
        "Taklifingiz qabul qilindi",
        f"«{job_title}» ishiga {float(proposal_price):,.0f} UZS taklifingiz qabul qilindi. Endi ish egasi to‘lovni amalga oshiradi.",
        f"/payments/job/{job_id}",
    )
    return jsonify({"msg": "Taklif qabul qilindi.", "worker_id": proposal_worker_id, "price": float(proposal_price)})

@app.route("/accept_job", methods=["POST"])
@auth
def accept():
    block_response=enforce_block("job_accept")
    if block_response: return block_response

    
    d = request.json or {}
    job_id = d.get("job_id")
    if not job_id:
        return jsonify({"msg": "Ish identifikatori ko‘rsatilmagan"}), 400

    try:
        job_id = int(job_id)
    except (TypeError, ValueError):
        return jsonify({"msg": "Ish identifikatori noto‘g‘ri"}), 400

    job = db.q("SELECT user_id, status, worker_id, title FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi"}), 404
    if job[0] == request.uid:
        return jsonify({"msg": "O'zingiz yaratgan ishni qabul qila olmaysiz!"}), 400
    if job[1] != "active":
        return jsonify({"msg": "Bu ish hozir qabul qilish uchun mavjud emas"}), 409
    if job[2] is not None:
        return jsonify({"msg": "Ushbu ish allaqachon qabul qilingan"}), 409

    held_payment = db.q(
        "SELECT payment_uuid,status,amount FROM payments WHERE job_id=? AND status='held' ORDER BY id DESC LIMIT 1",
        (job_id,),
    ).fetchone()

    if held_payment:
        result = db.q(
            "UPDATE jobs SET worker_id=?,status='accepted',finished_at=NULL WHERE id=? AND status='active' AND worker_id IS NULL AND user_id!=?",
            (request.uid, job_id, request.uid),
        )
    else:
        result = db.q(
            "UPDATE jobs SET worker_id=?,status='payment_pending' WHERE id=? AND status='active' AND worker_id IS NULL AND user_id!=?",
            (request.uid, job_id, request.uid),
        )
    updated = result.rowcount
    result.close()

    if updated != 1:
        return jsonify({"msg": "Ushbu ish allaqachon boshqa foydalanuvchi tomonidan qabul qilingan!"}), 409

    pending_proposals = db.q(
        "SELECT worker_id FROM job_proposals WHERE job_id=? AND status='pending'",
        (job_id,),
    ).fetchall()
    now_proposal_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.q(
        "UPDATE job_proposals SET status='rejected',updated_at=? WHERE job_id=? AND status='pending'",
        (now_proposal_time, job_id),
    ).close()
    for proposal_worker_id in [row[0] for row in pending_proposals]:
        create_notification(
            proposal_worker_id,
            "proposal_rejected",
            "Taklifingiz yopildi",
            f"«{job[3]}» ishini boshqa bajaruvchi qabul qildi, shuning uchun pending taklifingiz yopildi.",
            "/jobs",
        )

    if held_payment:
        db.q(
            "UPDATE payments SET payee_id=? WHERE job_id=? AND status='held'",
            (request.uid, job_id),
        ).close()
        create_notification(
            job[0],
            "worker_changed",
            "Ishchi almashtirildi — to‘lov waiting holatida",
            f"«{job[3]}» ishini yangi bajaruvchi qabul qildi. Oldingi to‘lov saqlanib turibdi va yangi bajaruvchiga ish yakunlangach o‘tkaziladi.",
            "/jobs",
        )
        create_notification(
            request.uid,
            "payment_held",
            "Ish uchun to‘lov allaqachon waiting holatida",
            f"«{job[3]}» uchun {float(held_payment[2]):,.0f} UZS to‘lov mavjud. Ishni yakunlangach va tasdiqlangach pul sizga o‘tkaziladi.",
            "/jobs",
        )
    else:
        create_notification(
            job[0],
            "job_accepted",
            "Ishingiz qabul qilindi — to‘lov kutilmoqda",
            f"Siz yaratgan «{job[3]}» nomli ishni bajaruvchi qabul qildi. Ishni boshlashdan oldin to‘lovni amalga oshiring.",
            f"/payments/job/{job_id}",
        )
    return jsonify({"msg": "ok"})
@app.route("/cancel_worker", methods=["POST"])
@auth
def cancel_worker():
    d = request.json or {}
    job_id = d.get("job_id")

    if not job_id:
        return jsonify({"msg": "Ish identifikatori ko‘rsatilmagan"}), 400

    try:
        job_id = int(job_id)
    except (TypeError, ValueError):
        return jsonify({"msg": "Ish identifikatori noto‘g‘ri"}), 400

    job = db.q("SELECT user_id, worker_id, status, title FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi"}), 404

    if job[0] != request.uid:
        return jsonify({"msg": "Faqat ish egasi bajaruvchini bekor qilishi mumkin"}), 403

    if job[1] is None:
        return jsonify({"msg": "Bu ishda hozir biriktirilgan bajaruvchi yo‘q"}), 400

    if job[2] not in ("payment_pending", "accepted"):
        return jsonify({"msg": "Bajaruvchini almashtirish faqat to‘lov kutilayotgan yoki waiting to‘lovi bor ishda mumkin"}), 400

    held_payment = db.q(
        "SELECT payment_uuid,status,amount FROM payments WHERE job_id=? AND status='held' ORDER BY id DESC LIMIT 1",
        (job_id,),
    ).fetchone()

    attachment_urls_to_remove = []
    conn = db.get_connection()
    cursor = conn.cursor()
    try:
        attachment_urls_to_remove = [
            row[0]
            for row in cursor.execute(
                "SELECT attachment_url FROM messages WHERE job_id=? AND attachment_url!=''",
                (job_id,),
            ).fetchall()
            if row[0]
        ]
        cursor.execute(
            "UPDATE jobs SET worker_id=NULL, status='active', finished_at=NULL, owner_finished=0, worker_finished=0 WHERE id=? AND user_id=? AND status IN ('payment_pending','accepted')",
            (job_id, request.uid),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify({"msg": "Ish holati o‘zgardi. Qayta urinib ko‘ring"}), 409

        cursor.execute("DELETE FROM messages WHERE job_id=?", (job_id,))
        if not held_payment:
            cursor.execute("DELETE FROM payments WHERE job_id=? AND status!='paid'", (job_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        return jsonify({"msg": "Bajaruvchini bekor qilishda xatolik yuz berdi"}), 500
    finally:
        conn.close()

    for attachment_url in attachment_urls_to_remove:
        _remove_stored_upload(attachment_url, "/uploads/chat/", CHAT_UPLOAD_DIR)

    if held_payment:
        create_notification(
            job[1],
            "worker_removed",
            "Ishdan chiqarildingiz",
            f"«{job[3]}» ishida bajaruvchi sifatida almashtirildingiz. To‘lov esa waiting holatida saqlanib qoldi.",
            "/jobs",
        )
    return jsonify({"msg": "ok", "status": "active", "payment_waiting": bool(held_payment)})
@app.route("/finish_job", methods=["POST"])
@auth
def finish():
    d = request.json or {}
    job_id = d.get("job_id")
    if not job_id:
        return jsonify({"msg": "Ish identifikatori ko‘rsatilmagan"}), 400
    try:
        job_id = int(job_id)
    except (TypeError, ValueError):
        return jsonify({"msg": "Ish identifikatori noto‘g‘ri"}), 400
    job = db.q("SELECT user_id,worker_id,status,owner_finished,worker_finished,title FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi"}), 404
    owner_id, worker_id, status, owner_finished, worker_finished, title = job
    if request.uid not in (owner_id, worker_id):
        return jsonify({"msg": "Faqat ish egasi yoki bajaruvchi yakunlashi mumkin"}), 403
    if not worker_id:
        return jsonify({"msg": "Ishni yakunlashdan oldin bajaruvchi tanlanishi kerak"}), 400
    if status != "accepted":
        return jsonify({"msg": "Ish hozir yakunlash uchun tayyor emas"}), 400

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        if request.uid == owner_id:
            cur.execute("UPDATE jobs SET owner_finished=1 WHERE id=? AND status='accepted'", (job_id,))
        else:
            cur.execute("UPDATE jobs SET worker_finished=1 WHERE id=? AND status='accepted'", (job_id,))
        state = cur.execute("SELECT owner_finished,worker_finished FROM jobs WHERE id=?", (job_id,)).fetchone()
        both_finished = bool(state and state[0] and state[1])
        if both_finished:
            now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("UPDATE jobs SET status='finished',finished_at=? WHERE id=? AND status='accepted'", (now_time, job_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if both_finished:
        release_payment = app.config.get("FINJOB_RELEASE_PAYMENT")
        if release_payment:
            ok, message, data = release_payment(job_id)
            if not ok:
                db.q("UPDATE jobs SET status='accepted',finished_at=NULL,owner_finished=0,worker_finished=0 WHERE id=? AND status='finished'", (job_id,)).close()
                return jsonify({"msg": message}), 400
        create_notification(owner_id, "job_finished", "Ish yakunlandi", f"«{title}» bo‘yicha ikkala tomon ham ishni yakunladi. Waiting to‘lovi bajaruvchiga o‘tkazildi.", "/jobs")
        create_notification(worker_id, "job_finished", "To‘lov balansingizga o‘tkazildi", f"«{title}» bo‘yicha ish yakunlandi va waiting to‘lovi balansingizga o‘tkazildi.", "/payments")
        return jsonify({"msg": "ok", "finished": True})

    other_id = worker_id if request.uid == owner_id else owner_id
    create_notification(request.uid, "job_finish_requested", "Yakunlash belgilandi", f"«{title}» bo‘yicha siz ishni yakunladingiz. Ikkinchi tomonning ham yakunlashini kuting.", "/jobs")
    create_notification(other_id, "job_finish_requested", "Ishni yakunlang", f"«{title}» bo‘yicha ikkinchi tomon ishni yakunladi. Siz ham «Yakunlash» tugmasini bosing.", "/jobs")
    return jsonify({"msg": "waiting", "finished": False})


CHAT_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "chat")
os.makedirs(CHAT_UPLOAD_DIR, exist_ok=True)
CHAT_ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp", "gif", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "zip"}
CHAT_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_CHAT_FILE_SIZE = 10 * 1024 * 1024


def _chat_file_type(stream):
    header = stream.read(16)
    stream.seek(0)
    if header.startswith(b"%PDF-"):
        return "pdf"
    if header.startswith(bytes.fromhex("504B0304")):
        return "zip"
    if header.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return "ole"
    if header.startswith(bytes.fromhex("89504E470D0A1A0A")):
        return "png"
    if header.startswith(bytes.fromhex("FFD8FF")):
        return "jpeg"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "webp"
    return ""


def _chat_participant(job_id, user_id):
    return db.q(
        """SELECT user_id, worker_id
           FROM jobs
           WHERE id=?
             AND worker_id IS NOT NULL
             AND status NOT IN ('active', 'blocked')
             AND (user_id=? OR worker_id=?)""",
        (job_id, user_id, user_id),
    ).fetchone()


@app.route("/message", methods=["POST"])
@auth
def send_message():
    block_response=enforce_block("chat")
    if block_response: return block_response

    
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        message_text = str(request.form.get("message", "")).strip()
        job_id_raw = request.form.get("job_id")
        receiver_id_raw = request.form.get("receiver_id")
        attachment = request.files.get("file")
    else:
        data = request.json or {}
        message_text = str(data.get("message", "")).strip()
        job_id_raw = data.get("job_id")
        receiver_id_raw = data.get("receiver_id")
        attachment = None

    try:
        job_id = int(job_id_raw)
    except (TypeError, ValueError):
        return jsonify({"msg": "Xabar ma'lumotlari noto'g'ri"}), 400

    job = _chat_participant(job_id, request.uid)
    if not job:
        return jsonify({"msg": "Bu chatga kirish huquqingiz yo'q"}), 403

    owner_id, worker_id = job
    if not worker_id:
        return jsonify({"msg": "Bu ishni hali hech kim qabul qilmagan"}), 400
    if receiver_id_raw in (None, ""):
        receiver_id = worker_id if request.uid == owner_id else owner_id
    else:
        try:
            receiver_id = int(receiver_id_raw)
        except (TypeError, ValueError):
            return jsonify({"msg": "Xabar ma'lumotlari noto'g'ri"}), 400
    if receiver_id not in (owner_id, worker_id) or receiver_id == request.uid:
        return jsonify({"msg": "Qabul qiluvchi ushbu chat ishtirokchisi emas"}), 403

    if not message_text and not attachment:
        return jsonify({"msg": "Xabar yoki fayl yuboring"}), 400
    if len(message_text) > 5000:
        return jsonify({"msg": "Xabar 5000 belgidan oshmasligi kerak"}), 400

    attachment_url = ""
    attachment_name = ""
    attachment_type = ""

    if attachment and attachment.filename:
        original_name = secure_filename(attachment.filename)
        if not original_name:
            return jsonify({"msg": "Fayl nomi noto'g'ri"}), 400
        extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
        if extension not in CHAT_ALLOWED_EXTENSIONS:
            return jsonify({"msg": "Bu fayl turi qo'llab-quvvatlanmaydi"}), 400

        attachment.seek(0, os.SEEK_END)
        size = attachment.tell()
        attachment.seek(0)
        if size > MAX_CHAT_FILE_SIZE:
            return jsonify({"msg": "Fayl hajmi 10 MB dan oshmasligi kerak"}), 400

        detected = _chat_file_type(attachment.stream)
        valid_image = extension in CHAT_IMAGE_EXTENSIONS and detected == ("jpeg" if extension in {"jpg", "jpeg"} else extension)
        valid_document = extension == "pdf" and detected == "pdf"
        valid_office = extension in {"doc", "xls", "ppt"} and detected == "ole"
        valid_office_zip = extension in {"docx", "xlsx", "pptx", "zip"} and detected == "zip"
        valid_text = extension == "txt"
        if not (valid_image or valid_document or valid_office or valid_office_zip or valid_text):
            return jsonify({"msg": "Fayl mazmuni uning kengaytmasiga mos kelmadi"}), 400

        stored_name = f"{uuid.uuid4().hex}.{extension}"
        filepath = os.path.join(CHAT_UPLOAD_DIR, stored_name)
        attachment.save(filepath)
        attachment_url = f"/uploads/chat/{stored_name}"
        attachment_name = original_name
        attachment_type = "image" if extension in CHAT_IMAGE_EXTENSIONS else extension

    now_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result = db.q(
        """INSERT INTO messages(sender_id,receiver_id,job_id,message,sent_at,read_at,attachment_url,attachment_name,attachment_type)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (request.uid, receiver_id, job_id, message_text, now_time, None, attachment_url, attachment_name, attachment_type),
    )
    result.close()
    return jsonify({"msg": "sent", "ok": True})


@app.route("/messages/<int:job_id>")
@auth
def get_messages(job_id):
    block_response=enforce_block("chat")
    if block_response: return block_response

    
    job = _chat_participant(job_id, request.uid)
    if not job:
        return jsonify({"msg": "Bu chatga kirish huquqingiz yo'q"}), 403

    db.q(
        "UPDATE messages SET read_at=? WHERE job_id=? AND receiver_id=? AND read_at IS NULL",
        (datetime.datetime.now(datetime.timezone.utc).isoformat(), job_id, request.uid),
    ).close()

    items = db.q(
        """SELECT m.id,m.sender_id,m.receiver_id,m.job_id,m.message,m.sent_at,m.read_at,
                  m.attachment_url,m.attachment_name,m.attachment_type,
                  CASE WHEN m.sender_id=u.id THEN TRIM(COALESCE(u.first_name,'') || ' ' || COALESCE(u.last_name,'')) ELSE '' END AS sender_name,
                  COALESCE(u.avatar_url,'') AS sender_avatar_url
           FROM messages m
           LEFT JOIN users u ON u.id=m.sender_id
           WHERE m.job_id=? ORDER BY m.id ASC LIMIT 500""",
        (job_id,),
    ).fetchall()

    return jsonify([
        {
            "id": x[0], "sender_id": x[1], "receiver_id": x[2], "job_id": x[3],
            "message": x[4] or "", "sent_at": x[5] or "", "read_at": x[6],
            "attachment_url": x[7] or "", "attachment_name": x[8] or "", "attachment_type": x[9] or "",
            "sender_name": x[10] or "", "sender_avatar_url": x[11] or ""
        }
        for x in items
    ])


@app.route("/admin/report/<int:report_id>/attachment")
@admin_required
def admin_report_attachment(report_id):
    row = db.q(
        """SELECT m.attachment_url
           FROM reports r
           JOIN messages m ON m.id=r.message_id
           WHERE r.id=?
           LIMIT 1""",
        (report_id,),
    ).fetchone()
    if not row or not row[0]:
        return jsonify({"msg": "Bu shikoyatga biriktirilgan fayl topilmadi"}),404
    attachment_url = row[0]
    prefix = "/uploads/chat/"
    if not attachment_url.startswith(prefix):
        return jsonify({"msg": "Biriktirilgan fayl manzili noto'g'ri"}),400
    filename = attachment_url[len(prefix):]
    if not filename or "/" in filename or "\\" in filename:
        return jsonify({"msg": "Biriktirilgan fayl nomi noto'g'ri"}),400
    filepath = os.path.join(CHAT_UPLOAD_DIR, filename)
    if not os.path.isfile(filepath):
        return jsonify({"msg": "Biriktirilgan fayl serverda topilmadi"}),404
    return send_from_directory(CHAT_UPLOAD_DIR, filename, as_attachment=False)

@app.route("/uploads/chat/<path:filename>")
@auth
def chat_upload(filename):
    row = db.q(
        """SELECT 1 FROM messages m
           JOIN jobs j ON j.id=m.job_id
           WHERE m.attachment_url=? AND (j.user_id=? OR j.worker_id=?)
           LIMIT 1""",
        (f"/uploads/chat/{filename}", request.uid, request.uid),
    ).fetchone()
    if not row:
        return jsonify({"msg": "Fayl topilmadi yoki ruxsat berilmadi"}), 404
    return send_from_directory(CHAT_UPLOAD_DIR, filename, as_attachment=False)


# -------- FAVORITES / PORTFOLIO / CHAT 2.0 --------
@app.route("/favorites", methods=["GET", "POST", "DELETE"])
@auth
def favorites():
    allowed_types = {"job", "user", "service"}

    if request.method == "GET":
        target_type = str(request.args.get("target_type", "")).strip().lower()
        if target_type and target_type not in allowed_types:
            return jsonify({"msg": "Sevimli obyekt turi noto‘g‘ri"}), 400
        sql = "SELECT target_type,target_id,created_at FROM favorites WHERE user_id=?"
        args = [request.uid]
        if target_type:
            sql += " AND target_type=?"
            args.append(target_type)
        sql += " ORDER BY id DESC LIMIT 500"
        items = db.q(sql, tuple(args)).fetchall()
        return jsonify([
            {"target_type": x[0], "target_id": x[1], "created_at": x[2]}
            for x in items
        ])

    data = request.json or {}
    target_type = str(data.get("target_type", "")).strip().lower()
    try:
        target_id = int(data.get("target_id"))
    except (TypeError, ValueError):
        return jsonify({"msg": "Obyekt ID raqami noto‘g‘ri"}), 400

    if target_type not in allowed_types or target_id <= 0:
        return jsonify({"msg": "Sevimli obyekt ma’lumoti noto‘g‘ri"}), 400

    if target_type == "job":
        target = db.q("SELECT id FROM jobs WHERE id=?", (target_id,)).fetchone()
    elif target_type == "user":
        target = db.q("SELECT id FROM users WHERE id=?", (target_id,)).fetchone()
    else:
        target = db.q("SELECT id FROM services WHERE id=?", (target_id,)).fetchone()
    if not target:
        return jsonify({"msg": "Saqlanadigan obyekt topilmadi"}), 404

    if request.method == "POST":
        db.q(
            "INSERT OR IGNORE INTO favorites(user_id,target_type,target_id,created_at) VALUES(?,?,?,?)",
            (request.uid,target_type,target_id,datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ).close()
        return jsonify({"msg": "ok", "favorited": True})

    db.q(
        "DELETE FROM favorites WHERE user_id=? AND target_type=? AND target_id=?",
        (request.uid,target_type,target_id),
    ).close()
    return jsonify({"msg": "ok", "favorited": False})


@app.route("/portfolio", methods=["GET", "POST"])
@auth
def portfolio():
    if request.method == "GET":
        username = str(request.args.get("username", "")).strip()
        owner_id = request.uid
        if username:
            owner = db.q("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if not owner:
                return jsonify({"msg": "Foydalanuvchi topilmadi"}), 404
            owner_id = owner[0]
        items = db.q(
            """SELECT id,title,description,url,image_url,file_url,file_name,created_at,updated_at
               FROM portfolio_items WHERE user_id=? ORDER BY id DESC LIMIT 50""",
            (owner_id,),
        ).fetchall()
        return jsonify([
            {"id": x[0],"title": x[1],"description": x[2],"url": x[3],"image_url": x[4],
             "file_url": x[5],"file_name": x[6],"created_at": x[7],"updated_at": x[8]}
            for x in items
        ])

    data = request.json or {}
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    url = str(data.get("url", "")).strip()
    image_url = str(data.get("image_url", "")).strip()
    if not title or len(title) > 120:
        return jsonify({"msg": "Portfolio nomi 1–120 belgidan iborat bo‘lishi kerak"}), 400
    if len(description) > 2000 or len(url) > 1000 or len(image_url) > 1000:
        return jsonify({"msg": "Portfolio maydonlaridan biri juda uzun"}), 400
    if url and not re.fullmatch(r"https?://\S+", url):
        return jsonify({"msg": "Portfolio havolasi noto‘g‘ri"}), 400
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result = db.q(
        """INSERT INTO portfolio_items(user_id,title,description,url,image_url,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?)""",
        (request.uid,title,description,url,image_url,now,now),
    )
    item_id = result.lastrowid
    result.close()
    return jsonify({"msg": "Portfolio qo‘shildi.", "id": item_id}), 201



    
PORTFOLIO_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "portfolio")
os.makedirs(PORTFOLIO_UPLOAD_DIR, exist_ok=True)
PORTFOLIO_ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp", "doc", "docx"}
PORTFOLIO_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_PORTFOLIO_FILE_SIZE = 10 * 1024 * 1024


@app.route("/portfolio/upload", methods=["POST"])
@auth
def upload_portfolio_file():
    count = db.q("SELECT COUNT(*) FROM portfolio_items WHERE user_id=?", (request.uid,)).fetchone()[0]
    if count >= 3:
        return jsonify({"ok": False, "msg": "Maksimal 3 ta portfolio qo‘shish mumkin."}), 400

    upload = request.files.get("file")
    raw_title = str(request.form.get("title", "")).strip()
    description = str(request.form.get("description", "")).strip()
    url = str(request.form.get("url", "")).strip()

    if not upload or not upload.filename:
        return jsonify({"ok": False, "msg": "Portfolio fayli tanlanmadi"}), 400

    original_filename = upload.filename.strip()
    fallback_title = os.path.splitext(secure_filename(original_filename))[0].strip()
    title = raw_title or fallback_title
    if not title or len(title) > 120:
        return jsonify({"ok": False, "msg": "Portfolio nomi 1–120 belgidan iborat bo‘lishi kerak"}), 400
    if len(description) > 2000 or len(url) > 1000:
        return jsonify({"ok": False, "msg": "Portfolio maydonlaridan biri juda uzun"}), 400
    if url and not re.fullmatch(r"https?://\S+", url):
        return jsonify({"msg": "Portfolio havolasi noto‘g‘ri"}), 400

    original_name = secure_filename(upload.filename)
    extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if extension not in PORTFOLIO_ALLOWED_EXTENSIONS:
        return jsonify({"msg": "Faqat PDF, PNG, JPG, JPEG yoki WEBP fayl yuklash mumkin"}), 400

    upload.seek(0, os.SEEK_END)
    size = upload.tell()
    upload.seek(0)
    if size > MAX_PORTFOLIO_FILE_SIZE:
        return jsonify({"msg": "Portfolio fayli 10 MB dan oshmasligi kerak"}), 400

    try:
        stored_extension = extension
        if extension in PORTFOLIO_IMAGE_EXTENSIONS:
            Image.MAX_IMAGE_PIXELS = 20_000_000
            source = Image.open(upload.stream)
            source.verify()
            upload.stream.seek(0)
            image = Image.open(upload.stream)
            image = ImageOps.exif_transpose(image)
            if image.width * image.height > 20_000_000:
                return jsonify({"msg": "Rasm o‘lchami juda katta"}), 400
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            stored_extension = "webp"
            stored_name = f"{uuid.uuid4().hex}.{stored_extension}"
            filepath = os.path.join(PORTFOLIO_UPLOAD_DIR, stored_name)
            image.save(filepath, "WEBP", quality=86, method=6)
            image.close()
            source.close()
        else:
            header = upload.stream.read(8)
            upload.stream.seek(0)
            valid_pdf = extension == "pdf" and header.startswith(b"%PDF-")
            valid_doc = extension == "doc" and header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
            valid_docx = extension == "docx" and header.startswith(b"PK\x03\x04")
            if not (valid_pdf or valid_doc or valid_docx):
                return jsonify({"msg": "Yuklangan fayl formati yoki tarkibi noto‘g‘ri"}), 400
            stored_name = f"{uuid.uuid4().hex}.{stored_extension}"
            filepath = os.path.join(PORTFOLIO_UPLOAD_DIR, stored_name)
            upload.save(filepath)
    except (UnidentifiedImageError, OSError, ValueError):
        return jsonify({"msg": "Yuklangan faylni tekshirishda xatolik yuz berdi"}), 400

    file_url = f"/uploads/portfolio/{stored_name}"
    image_url = file_url if extension in PORTFOLIO_IMAGE_EXTENSIONS else ""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        result = db.q(
            """INSERT INTO portfolio_items(
                   user_id,title,description,url,image_url,file_url,file_name,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (request.uid,title,description,url,image_url,file_url,original_name or stored_name,now,now),
        )
        item_id = result.lastrowid
        result.close()
    except Exception:
        if os.path.isfile(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
        return jsonify({"ok": False, "msg": "Portfolio ma'lumotini saqlashda xatolik yuz berdi"}), 500

    return jsonify({
        "ok": True,
        "msg": "Portfolio qo‘shildi.",
        "id": item_id,
        "file_url": file_url,
        "file_name": original_name or stored_name,
        "image_url": image_url,
    }), 201


@app.route("/uploads/portfolio/<path:filename>")
def portfolio_upload(filename):
    return send_from_directory(PORTFOLIO_UPLOAD_DIR, filename)


@app.route("/portfolio/<int:item_id>", methods=["PATCH", "DELETE"])
@auth
def update_portfolio(item_id):
    item = db.q("SELECT user_id FROM portfolio_items WHERE id=?", (item_id,)).fetchone()
    if not item:
        return jsonify({"msg": "Portfolio topilmadi"}), 404
    if item[0] != request.uid:
        return jsonify({"msg": "Ruxsat berilmadi"}), 403

    if request.method == "DELETE":
        item = db.q("SELECT file_url FROM portfolio_items WHERE id=?", (item_id,)).fetchone()
        db.q("DELETE FROM portfolio_items WHERE id=?", (item_id,)).close()

        if item and item[0] and item[0].startswith("/uploads/portfolio/"):
            filename = item[0].rsplit("/", 1)[-1]
            filepath = os.path.join(PORTFOLIO_UPLOAD_DIR, filename)
            if os.path.isfile(filepath):
                try:
                    os.remove(filepath)
                except OSError:
                    pass
        return jsonify({"msg": "Portfolio o‘chirildi."})

    data = request.json or {}
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    url = str(data.get("url", "")).strip()
    image_url = str(data.get("image_url", "")).strip()
    if not title or len(title) > 120 or len(description) > 2000 or len(url) > 1000 or len(image_url) > 1000:
        return jsonify({"msg": "Portfolio ma’lumotlari noto‘g‘ri"}), 400
    if url and not re.fullmatch(r"https?://\S+", url):
        return jsonify({"msg": "Portfolio havolasi noto‘g‘ri"}), 400
    db.q(
        "UPDATE portfolio_items SET title=?,description=?,url=?,image_url=?,updated_at=? WHERE id=?",
        (title,description,url,image_url,datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),item_id),
    ).close()
    return jsonify({"msg": "Portfolio yangilandi."})


@app.route("/messages/unread-count")
@auth
def unread_message_count():
    count = db.q(
        "SELECT COUNT(*) FROM messages WHERE receiver_id=? AND read_at IS NULL",
        (request.uid,),
    ).fetchone()[0]
    return jsonify({"unread": int(count)})


@app.route("/conversations")
@auth
def conversations():
    block_response = enforce_block("chat")
    if block_response:
        return block_response

    items = db.q(
        """SELECT m.id,m.job_id,m.sender_id,m.receiver_id,m.message,m.sent_at,m.read_at,j.title,
                  CASE WHEN m.sender_id=? THEN r.username ELSE s.username END as other_username,
                  (SELECT COUNT(*) FROM messages unread
                   WHERE unread.job_id=m.job_id AND unread.receiver_id=? AND unread.read_at IS NULL) as unread_count
           FROM messages m
           JOIN jobs j ON j.id=m.job_id
           LEFT JOIN users s ON s.id=m.sender_id
           LEFT JOIN users r ON r.id=m.receiver_id
           WHERE j.worker_id IS NOT NULL
             AND j.status NOT IN ('active', 'blocked')
             AND (m.sender_id=? OR m.receiver_id=?)
             AND m.id IN (
               SELECT MAX(m2.id) FROM messages m2
               WHERE m2.sender_id=? OR m2.receiver_id=?
               GROUP BY m2.job_id
           )
           ORDER BY m.id DESC LIMIT 100""",
        (request.uid,request.uid,request.uid,request.uid,request.uid,request.uid),
    ).fetchall()

    return jsonify([
        {
            "job_id": x[1], "sender_id": x[2], "receiver_id": x[3], "message": x[4],
            "sent_at": x[5], "read_at": x[6], "title": x[7], "other_username": x[8] or "",
            "unread": int(x[9] or 0)
        }
        for x in items
    ])


@app.route("/presence", methods=["POST"])
@auth
def update_presence():
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db.q("UPDATE users SET last_seen_at=? WHERE id=?", (now,request.uid)).close()
    return jsonify({"ok":True,"last_seen_at":now})


@app.route("/presence/<int:user_id>")
@auth
def get_presence(user_id):
    if user_id != request.uid:
        block_response = enforce_block("chat")
        if block_response:
            return block_response
        raw_job_id = request.args.get("job_id")
        try:
            presence_job_id = int(raw_job_id)
        except (TypeError, ValueError):
            return jsonify({"msg":"Presence ma’lumotini olish uchun chat identifikatori talab qilinadi"}),403

        chat_job = _chat_participant(presence_job_id, request.uid)
        if not chat_job or user_id not in chat_job:
            return jsonify({"msg":"Presence ma’lumotiga ruxsat berilmadi"}),403

    row = db.q("SELECT last_seen_at FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        return jsonify({"msg":"Foydalanuvchi topilmadi"}),404
    online=False
    last_seen=row[0] or ""
    if last_seen:
        try:
            seen=datetime.datetime.fromisoformat(last_seen)
            online=(datetime.datetime.now(datetime.timezone.utc)-seen).total_seconds()<=75
        except ValueError:
            pass
    return jsonify({"online":online,"last_seen_at":last_seen})


@app.route("/typing/<int:job_id>", methods=["GET", "POST"])
@auth
def typing(job_id):
    block_response=enforce_block("chat")
    if block_response: return block_response

    
    job = _chat_participant(job_id, request.uid)
    if not job:
        return jsonify({"msg":"Bu chatga kirish huquqingiz yo‘q"}),403
    now=time.time()
    conn=db.get_connection()
    try:
        conn.execute("DELETE FROM typing_states WHERE updated_at < ?", (now-8,))
        if request.method=="POST":
            active=bool((request.json or {}).get("typing"))
            if active:
                conn.execute(
                    "INSERT INTO typing_states(job_id,user_id,updated_at) VALUES(?,?,?) ON CONFLICT(job_id,user_id) DO UPDATE SET updated_at=excluded.updated_at",
                    (job_id,request.uid,now),
                )
            else:
                conn.execute("DELETE FROM typing_states WHERE job_id=? AND user_id=?", (job_id,request.uid))
        row=conn.execute(
            "SELECT user_id,updated_at FROM typing_states WHERE job_id=? AND user_id!=?",
            (job_id,request.uid),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    return jsonify({"typing":bool(row and now-row[1]<=4)})


# -------- RATINGS --------
@app.route("/rating", methods=["POST"])
@auth
def add_rating():
    block_response=enforce_block("rating")
    if block_response: return block_response

    
    d = request.json or {}
    job_id = d.get("job_id")
    to_user = d.get("to_user")
    score = d.get("score")
    comment = str(d.get("comment", "")).strip()

    if not job_id or to_user is None or score is None:
        return jsonify({"msg": "Ish identifikatori, baho beriladigan foydalanuvchi va ball kiritilishi shart"}), 400

    try:
        score = int(score)
        to_user = int(to_user)
        job_id = int(job_id)
    except (ValueError, TypeError):
        return jsonify({"msg": "Noto'g'ri ma'lumot formati"}), 400

    if score < 1 or score > 10:
        return jsonify({"msg": "Baho 1 dan 10 gacha bo'lishi kerak"}), 400
    if len(comment) > 2000:
        return jsonify({"msg": "Izoh 2000 belgidan oshmasligi kerak"}), 400

    if request.uid == to_user:
        return jsonify({"msg": "O'zingizga baho bera olmaysiz!"}), 400

    job = db.q("SELECT user_id, worker_id, status FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi"}), 404

    if job[1] is None:
        return jsonify({"msg": "Bu ishda hali bajaruvchi yo'q"}), 400

    if job[2] != "finished":
        return jsonify({"msg": "Ish tugamaguncha baho berib bo'lmaydi"}), 400
    if request.uid != job[0] and request.uid != job[1]:
        return jsonify({"msg": "Siz ushbu ish ishtirokchisi emassiz"}), 403

    other_user = job[1] if request.uid == job[0] else job[0]
    if to_user != other_user:
        return jsonify({"msg": "Faqat ushbu ishdagi boshqa ishtirokchini baholashingiz mumkin"}), 400
    if db.q("SELECT id FROM ratings WHERE job_id=? AND from_user=?", (job_id, request.uid)).fetchone():
        return jsonify({"msg": "Bu ish uchun siz allaqachon baho bergansiz"}), 409

    now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        result = db.q(
            "INSERT INTO ratings(job_id, from_user, to_user, score, comment, created_at) VALUES(?,?,?,?,?,?)",
            (job_id, request.uid, to_user, score, comment, now_time),
        )
        result.close()
    except sqlite3.IntegrityError:
        return jsonify({"msg": "Bu ish uchun siz allaqachon baho bergansiz"}), 409

    avg_row = db.q("SELECT AVG(score) FROM ratings WHERE to_user=?", (to_user,)).fetchone()
    avg_score = round(avg_row[0], 1) if avg_row and avg_row[0] is not None else 0.0
    result = db.q("UPDATE users SET average_rating=? WHERE id=?", (avg_score, to_user))
    result.close()

    return jsonify({"msg": "ok", "average_rating": avg_score})


# -------- LEADERBOARD --------
@app.route("/leaderboard")
@auth
def get_leaderboard():
    creators_raw = db.q(
        """SELECT u.id, u.first_name, u.last_name, u.username, COUNT(j.id) as count 
           FROM jobs j 
           JOIN users u ON j.user_id = u.id 
           WHERE j.status = 'finished' 
           GROUP BY u.id 
           ORDER BY count DESC 
           LIMIT 10"""
    ).fetchall()
    creators = [
        {"id": i[0], "name": f"{i[1]} {i[2]}".strip() if (i[1] or i[2]) else i[3], "username": i[3], "count": i[4]}
        for i in creators_raw
    ]

    workers_raw = db.q(
        """SELECT u.id, u.first_name, u.last_name, u.username, COUNT(j.id) as count 
           FROM jobs j 
           JOIN users u ON j.worker_id = u.id 
           WHERE j.status = 'finished' 
           GROUP BY u.id 
           ORDER BY count DESC 
           LIMIT 10"""
    ).fetchall()
    workers = [
        {"id": i[0], "name": f"{i[1]} {i[2]}".strip() if (i[1] or i[2]) else i[3], "username": i[3], "count": i[4]}
        for i in workers_raw
    ]

    return jsonify({"creators": creators, "workers": workers})


# -------- PROFILE PHOTO --------
PROFILE_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "profile_pictures")
os.makedirs(PROFILE_UPLOAD_DIR, exist_ok=True)
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_PROFILE_IMAGE_SIZE = 5 * 1024 * 1024


def _remove_stored_upload(url, prefix, base_dir):
    if not url or not isinstance(url, str) or not url.startswith(prefix):
        return
    relative = url[len(prefix):].lstrip("/")
    if not relative or "/" in relative or "\\" in relative:
        return
    root = os.path.abspath(base_dir)
    path = os.path.abspath(os.path.join(root, relative))
    try:
        if os.path.commonpath([root, path]) != root:
            return
    except ValueError:
        return
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


@app.route("/profile/avatar", methods=["POST"])
@auth
def upload_profile_avatar():
    image = request.files.get("image")
    if not image or not image.filename:
        return jsonify({"msg": "Rasm tanlanmadi"}), 400

    extension = image.filename.rsplit(".", 1)[-1].lower() if "." in image.filename else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({"msg": "Faqat PNG, JPG, JPEG yoki WEBP rasm yuklash mumkin"}), 400

    image.seek(0, os.SEEK_END)
    size = image.tell()
    image.seek(0)
    if size > MAX_PROFILE_IMAGE_SIZE:
        return jsonify({"msg": "Rasm hajmi 5 MB dan oshmasligi kerak"}), 400

    try:
        Image.MAX_IMAGE_PIXELS = 20_000_000
        source = Image.open(image.stream)
        source.verify()
        image.stream.seek(0)
        avatar = Image.open(image.stream)
        avatar = ImageOps.exif_transpose(avatar)
        if avatar.width * avatar.height > 20_000_000:
            return jsonify({"msg": "Rasm o‘lchami juda katta"}), 400
        if avatar.mode not in ("RGB", "RGBA"):
            avatar = avatar.convert("RGBA" if "A" in avatar.getbands() else "RGB")
        filename = f"{request.uid}_{uuid.uuid4().hex}.webp"
        filepath = os.path.join(PROFILE_UPLOAD_DIR, filename)
        avatar.save(filepath, "WEBP", quality=85, method=6)
        avatar.close()
        source.close()
    except (UnidentifiedImageError, OSError, ValueError):
        return jsonify({"msg": "Yuklangan fayl haqiqiy rasm emas"}), 400

    avatar_url = f"/uploads/profile_pictures/{filename}"
    old_avatar = db.q("SELECT avatar_url FROM users WHERE id=?", (request.uid,)).fetchone()
    old_url = old_avatar[0] if old_avatar else ""
    result = db.q("UPDATE users SET avatar_url=? WHERE id=?", (avatar_url, request.uid))
    result.close()

    if old_url and old_url.startswith("/uploads/profile_pictures/"):
        old_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), old_url.lstrip("/").replace("/", os.sep))
        if os.path.isfile(old_path) and old_path != filepath:
            try:
                os.remove(old_path)
            except OSError:
                pass

    return jsonify({"msg": "ok", "avatar_url": avatar_url})


@app.route("/uploads/profile_pictures/<path:filename>")
def profile_avatar(filename):
    return send_from_directory(PROFILE_UPLOAD_DIR, filename)


# -------- PUBLIC PROFILES --------
@app.route("/profiles/<string:username>", methods=["GET"])
@auth
def public_profile(username):
    username = username.strip()
    if not username:
        return jsonify({"msg": "Foydalanuvchi nomi kiritilmagan"}), 400

    u = db.q(
        """SELECT id, username, first_name, last_name, email, birthday, bio, skills, created_at,
                  average_rating, role, avatar_url
           FROM users
           WHERE username=?""",
        (username,),
    ).fetchone()
    if not u:
        return jsonify({"msg": "Foydalanuvchi topilmadi"}), 404

    created_jobs_count = db.q("SELECT COUNT(*) FROM jobs WHERE user_id=?", (u[0],)).fetchone()[0]
    completed_jobs_count = db.q(
        "SELECT COUNT(*) FROM jobs WHERE worker_id=? AND status='finished'", (u[0],)
    ).fetchone()[0]
    rating_res = db.q("SELECT AVG(score) FROM ratings WHERE to_user=?", (u[0],)).fetchone()[0]
    avg_rating = round(float(rating_res), 1) if rating_res is not None else 0.0
    reviews_count = db.q("SELECT COUNT(*) FROM ratings WHERE to_user=?", (u[0],)).fetchone()[0]
    worker_jobs = db.q("SELECT COUNT(*) FROM jobs WHERE worker_id=?", (u[0],)).fetchone()[0]
    successful_worker_jobs = db.q("SELECT COUNT(*) FROM jobs WHERE worker_id=? AND status='finished'", (u[0],)).fetchone()[0]
    success_rate = round((successful_worker_jobs / worker_jobs) * 100, 1) if worker_jobs else 0.0
    portfolio_rows = db.q(
        """SELECT id,title,description,url,image_url,file_url,file_name,created_at,updated_at
           FROM portfolio_items WHERE user_id=? ORDER BY id DESC LIMIT 50""",
        (u[0],),
    ).fetchall()

    visible_email = u[4] or "" if (u[0] == request.uid or getattr(request, "user_role", "user") == "admin") else ""

    return jsonify({
        "id": u[0],
        "username": u[1],
        "first_name": u[2] or "",
        "last_name": u[3] or "",
        "email": visible_email,
        "bio": u[6] or "",
        "skills": u[7] or "",
        "created_at": u[8] or "",
        "average_rating": avg_rating,
        "avg_rating": avg_rating,
        "role": u[10] or "user",
        "avatar_url": u[11] or "",
        "verification": _verification_payload(u[0]),
        "reputation": _reputation_payload(u[0]),
        "created_jobs_count": created_jobs_count,
        "completed_jobs_count": completed_jobs_count,
        "reviews_count": reviews_count,
        "success_rate": success_rate,
        "portfolio": [
            {"id": x[0], "title": x[1], "description": x[2], "url": x[3], "image_url": x[4],
             "file_url": x[5], "file_name": x[6], "created_at": x[7], "updated_at": x[8]}
            for x in portfolio_rows
        ],
    })


# -------- PROFILE --------
@app.route("/profile", methods=["GET", "PUT"])
@auth
def profile():
    if request.method == "GET":
        u = db.q(
            "SELECT id, username, first_name, last_name, email, birthday, bio, skills, created_at, average_rating, role, avatar_url, COALESCE(balance, 0) FROM users WHERE id=?",
            (request.uid,),
        ).fetchone()
        if not u:
            return jsonify({"msg": "Foydalanuvchi topilmadi"}), 404

        created_jobs_count = db.q("SELECT COUNT(*) FROM jobs WHERE user_id=?", (request.uid,)).fetchone()[0]
        completed_jobs_count = db.q(
            "SELECT COUNT(*) FROM jobs WHERE worker_id=? AND status='finished'", (request.uid,)
        ).fetchone()[0]

        rating_res = db.q("SELECT AVG(score) FROM ratings WHERE to_user=?", (request.uid,)).fetchone()[0]
        avg_rating = round(rating_res, 1) if rating_res is not None else 0.0
        user_role = u[10] if len(u) > 10 and u[10] else "user"
        avatar_url = u[11] if len(u) > 11 and u[11] else ""
        balance = float(u[12] or 0)
        portfolio_rows = db.q(
            """SELECT id,title,description,url,image_url,file_url,file_name,created_at,updated_at
               FROM portfolio_items WHERE user_id=? ORDER BY id DESC LIMIT 50""",
            (request.uid,),
        ).fetchall()

        return jsonify({
            "id": u[0],
            "username": u[1],
            "first_name": u[2] or "",
            "last_name": u[3] or "",
            "email": u[4] or "",
            "birthday": u[5] or "",
            "bio": u[6] or "",
            "skills": u[7] or "",
            "created_at": u[8] or "",
            "average_rating": avg_rating,
            "role": user_role,
            "created_jobs_count": created_jobs_count,
            "completed_jobs_count": completed_jobs_count,
            "avg_rating": avg_rating,
            "avatar_url": avatar_url,
            "balance": balance,
            "verification": _verification_payload(request.uid),
            "reputation": _reputation_payload(request.uid),
            "active_blocks": [_block_payload(x) for x in _active_block_row(request.uid)],
            "portfolio": [
                {"id": x[0], "title": x[1], "description": x[2], "url": x[3], "image_url": x[4],
                 "file_url": x[5], "file_name": x[6], "created_at": x[7], "updated_at": x[8]}
                for x in portfolio_rows
            ],
        })

    elif request.method == "PUT":
        d = request.json or {}
        username = str(d.get("username", "")).strip()
        email = str(d.get("email", "")).strip().lower()

        if not username or not email:
            return jsonify({"msg": "Foydalanuvchi nomi va elektron pochta kiritilishi shart"}), 400
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
            return jsonify({"msg": "Foydalanuvchi nomi 3–32 belgidan iborat bo‘lishi kerak"}), 400
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
            return jsonify({"msg": "Elektron pochta manzili noto‘g‘ri"}), 400

        first_name = str(d.get("first_name", "")).strip()
        last_name = str(d.get("last_name", "")).strip()
        birthday = str(d.get("birthday", "")).strip()
        bio = str(d.get("bio", "")).strip()
        skills = str(d.get("skills", "")).strip()
        if len(first_name) > 100 or len(last_name) > 100 or len(birthday) > 32 or len(bio) > 2000 or len(skills) > 2000:
            return jsonify({"msg": "Profil maydonlaridan biri juda uzun"}), 400

        exists_u = db.q("SELECT id FROM users WHERE username=? AND id!=?", (username, request.uid)).fetchone()
        if exists_u:
            return jsonify({"msg": "Ushbu foydalanuvchi nomi allaqachon band!"}), 400

        current_email_row = db.q("SELECT email FROM users WHERE id=?", (request.uid,)).fetchone()
        current_email = str(current_email_row[0] or "").strip().lower() if current_email_row else ""
        if email != current_email:
            return jsonify({
                "msg": "Elektron pochta manzilini oddiy profil tahriridan o‘zgartirib bo‘lmaydi. Avval qayta autentifikatsiya va email tasdiqlash jarayoni kerak.",
                "email_change_required": True
            }), 409

        exists_e = db.q("SELECT id FROM users WHERE email=? AND id!=?", (email, request.uid)).fetchone()
        if exists_e:
            return jsonify({"msg": "Ushbu elektron pochta allaqachon ro‘yxatdan o‘tgan!"}), 400

        try:
            result = db.q(
                """UPDATE users
                   SET first_name=?, last_name=?, birthday=?, username=?, email=?, bio=?, skills=?
                   WHERE id=?""",
                (
                    first_name,
                    last_name,
                    birthday,
                    username,
                    email,
                    bio,
                    skills,
                    request.uid,
                ),
            )
            result.close()
        except sqlite3.IntegrityError:
            return jsonify({"msg": "Foydalanuvchi nomi yoki elektron pochta boshqa hisobda band"}), 409

        return jsonify({"msg": "ok"})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
