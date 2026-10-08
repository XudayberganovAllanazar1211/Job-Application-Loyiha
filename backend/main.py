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