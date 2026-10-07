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
    "/register/send-code": (3, 900),
    "/register/verify": (10, 900),
    "/message": (60, 60),
    "/report": (10, 600),
    "/wallet/withdraw": (10, 600),
    "/payments/dummy/": (10, 60),
}


def _rate_limit_key(path):
    ip = request.remote_addr or "unknown"
    extra = ""
    payload = request.get_json(silent=True) or {}
    if path == "/login":
        extra = ":" + str(payload.get("username", "")).strip().lower()[:254]
    elif path in ("/register/send-code", "/register/verify"):
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
    blocked, retry_after = _rate_limited(request.path) if request.method in {"POST", "PATCH"} else (False, 0)
    if blocked:
        response = jsonify({"msg": "Juda ko‘p so‘rov yuborildi. Birozdan keyin qayta urinib ko‘ring."})
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response
    return None

# -------- E-MAIL (SMTP) SOZLAMALARI --------
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# Vaqtinchalik tasdiqlash kodlarini xotirada saqlash uchun lug'at:
# email -> { "code": str, "data": dict, "expiry": datetime }
pending_verifications = {}


def send_email_code(to_email, code):
    subject = "FinJob - Ro'yxatdan o'tish kodi"
    body = f"Sizning 6 xonali ro'yxatdan o'tish kodingiz: {code}\nUshbu kodni hech kimga bermang."

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        app.logger.exception("Tasdiqlash xatini yuborishda xatolik yuz berdi: %s", e)
        return False


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
        conn.execute("PRAGMA cache_size = 10000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

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
                read_at TEXT,
                attachment_url TEXT DEFAULT '',
                attachment_name TEXT DEFAULT '',
                attachment_type TEXT DEFAULT ''
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
        cursor.execute(
            "INSERT OR IGNORE INTO platform_settings(key,value) VALUES('commission_percent','10')"
        )
        cursor.execute("INSERT OR IGNORE INTO platform_wallet(id,balance,escrow_balance) VALUES(1,0,0)")

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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_job ON messages(job_id, sent_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_receiver_read ON messages(receiver_id, read_at, sent_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_proposals_job_status ON job_proposals(job_id, status, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_proposals_worker_status ON job_proposals(worker_id, status, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_favorites_user_target ON favorites(user_id, target_type, target_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_user_created ON portfolio_items(user_id, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_payer_status ON payments(payer_id,status,created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_payee_status ON payments(payee_id,status,created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_job_status ON payments(job_id,status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user ON wallet_transactions(user_id,created_at);")
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
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, args)
            conn.commit()
            return QueryResult(conn, cursor)
        except Exception:
            conn.rollback()
            conn.close()
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
        if self.conn is not None:
            self.conn.close()
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
            user = db.q("SELECT role, COALESCE(token_version,0) FROM users WHERE id=?", (uid,)).fetchone()
            if not user:
                return jsonify({"msg": "Kirish tokeni yaroqsiz"}), 401
            if int(d.get("ver", -1)) != int(user[1] or 0):
                return jsonify({"msg": "Sessiya muddati tugagan. Qayta kiring."}), 401
            request.uid = uid
            request.user_role = user[0] or "user"
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


register_payment_routes(app, db, auth, admin_required, create_notification)
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
    if header.startswith(b"PK\\x03\\x04"):
        return "zip"
    if header.startswith(b"\\xD0\\xCF\\x11\\xE0\\xA1\\xB1\\x1A\\xE1"):
        return "ole"
    if header.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
        return "png"
    if header.startswith(b"\\xff\\xd8\\xff"):
        return "jpeg"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "webp"
    return ""


def _chat_participant(job_id, user_id):
    return db.q(
        "SELECT user_id, worker_id FROM jobs WHERE id=? AND (user_id=? OR worker_id=?)",
        (job_id, user_id, user_id),
    ).fetchone()


@app.route("/message", methods=["POST"])
@auth
def send_message():
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
        receiver_id = int(receiver_id_raw)
    except (TypeError, ValueError):
        return jsonify({"msg": "Xabar ma'lumotlari noto'g'ri"}), 400

    job = _chat_participant(job_id, request.uid)
    if not job:
        return jsonify({"msg": "Bu chatga kirish huquqingiz yo'q"}), 403

    owner_id, worker_id = job
    if not worker_id or receiver_id not in (owner_id, worker_id) or receiver_id == request.uid:
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
                  CASE WHEN m.sender_id=u.id THEN TRIM(COALESCE(u.first_name,'') || ' ' || COALESCE(u.last_name,'')) ELSE '' END AS sender_name
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
            "sender_name": x[10] or ""
        }
        for x in items
    ])


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
    except (TypeError,ValueError):
        return jsonify({"msg":"Identifikator noto‘g‘ri"}),400
    if not reason or len(reason)>120:
        return jsonify({"msg":"Shikoyat sababini kiriting"}),400
    if len(details)>2000:
        return jsonify({"msg":"Izoh 2000 belgidan oshmasligi kerak"}),400
    if reported_user_id == request.uid:
        return jsonify({"msg":"O‘zingiz ustingizdan shikoyat qila olmaysiz"}),400
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

    if job_status not in ("accepted", "pending_finish"):
        return jsonify({"msg":"Bu ish bo‘yicha hozircha shikoyat qilish mumkin emas"}),400

    target_user_id = worker_id if request.uid == owner_id else owner_id
    if reported_user_id != target_user_id:
        return jsonify({"msg":"Faqat shu ishdagi boshqa ishtirokchi haqida shikoyat qilish mumkin"}),403

    now_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.q("INSERT INTO reports(reporter_id,reported_user_id,job_id,reason,details,created_at) VALUES(?,?,?,?,?,?)",(request.uid,reported_user_id,job_id,reason,details,now_time)).close()
    for admin in db.q("SELECT id FROM users WHERE role='admin'").fetchall():
        create_notification(admin[0],"report","Yangi shikoyat",reason,"/admin")
    return jsonify({"msg":"Shikoyatingiz qabul qilindi."}),201


@app.route("/admin/report/<int:report_id>", methods=["PATCH"])
@admin_required
def update_report(report_id):
    status=(request.json or {}).get("status")
    if status not in ("open","reviewing","resolved","rejected"):
        return jsonify({"msg":"Report holati noto‘g‘ri"}),400

    report=db.q(
        "SELECT reporter_id, reported_user_id, job_id, status FROM reports WHERE id=?",
        (report_id,)
    ).fetchone()
    if not report:
        return jsonify({"msg":"Shikoyat topilmadi"}),404

    reporter_id, reported_user_id, job_id, old_status = report
    result=db.q("UPDATE reports SET status=? WHERE id=?",(status,report_id))
    if result.rowcount!=1:
        result.close()
        return jsonify({"msg":"Shikoyat topilmadi"}),404
    result.close()

    if status in ("resolved", "rejected") and old_status != status:
        if status == "resolved":
            if job_id:
                refund_payment = app.config.get("FINJOB_REFUND_PAYMENT")
                if refund_payment:
                    refund_ok, refund_message, refund_data = refund_payment(job_id)
                    if not refund_ok and refund_message not in ("Faqat waiting holatidagi to‘lovni refund qilish mumkin",):
                        db.q("UPDATE reports SET status=? WHERE id=?", (old_status, report_id)).close()
                        return jsonify({"msg": refund_message}), 400
                db.q(
                    "UPDATE jobs SET status='blocked', finished_at=NULL, owner_finished=0, worker_finished=0 WHERE id=?",
                    (job_id,)
                ).close()

            create_notification(
                reporter_id,
                "report_resolved",
                "Shikoyat hal qilindi",
                "Siz yuborgan shikoyat admin tomonidan ko‘rib chiqildi va ish bloklandi.",
                "/jobs"
            )
            create_notification(
                reported_user_id,
                "report_resolved",
                "Shikoyat bo‘yicha qaror",
                "Siz qatnashgan ish bo‘yicha shikoyat admin tomonidan ko‘rib chiqildi va ish bloklandi.",
                "/jobs"
            )
        else:
            create_notification(
                reporter_id,
                "report_rejected",
                "Shikoyat rad etildi",
                "Siz yuborgan shikoyat admin tomonidan ko‘rib chiqildi va rad etildi.",
                "/jobs"
            )
            create_notification(
                reported_user_id,
                "report_rejected",
                "Shikoyat rad etildi",
                "Siz qatnashgan ish bo‘yicha berilgan shikoyat admin tomonidan rad etildi.",
                "/jobs"
            )

    return jsonify({"msg":"Shikoyat holati yangilandi","status":status})


# -------- ADMIN --------
@app.route("/admin/overview")
@admin_required
def admin_overview():
    users = db.q(
        """SELECT id, username, first_name, last_name, email, birthday, bio, skills, role, created_at, average_rating, COALESCE(balance,0)
           FROM users ORDER BY id DESC"""
    ).fetchall()

    jobs = db.q(
        """SELECT j.id, j.title, j.price, j.currency, j.location, j.status, j.created_at,
                  u.username AS creator_username,
                  w.username AS worker_username
           FROM jobs j
           LEFT JOIN users u ON u.id = j.user_id
           LEFT JOIN users w ON w.id = j.worker_id
           ORDER BY j.id DESC"""
    ).fetchall()

    services = db.q(
        """SELECT s.id, s.name, s.parent_id, p.name AS parent_name, s.created_by
           FROM services s
           LEFT JOIN services p ON p.id = s.parent_id
           ORDER BY s.id DESC"""
    ).fetchall()

    ratings = db.q(
        """SELECT r.id, r.job_id, r.score, r.comment, r.created_at,
                  f.username AS from_username, t.username AS to_username
           FROM ratings r
           LEFT JOIN users f ON f.id = r.from_user
           LEFT JOIN users t ON t.id = r.to_user
           ORDER BY r.id DESC"""
    ).fetchall()

    reports = db.q(
        """SELECT r.id, r.reason, r.details, r.status, r.created_at,
                  f.username AS reporter_username, t.username AS reported_username
           FROM reports r
           LEFT JOIN users f ON f.id = r.reporter_id
           LEFT JOIN users t ON t.id = r.reported_user_id
           ORDER BY r.id DESC"""
    ).fetchall()

    commission_row = db.q(
        "SELECT value FROM platform_settings WHERE key='commission_percent'"
    ).fetchone()
    commission_percent = float(commission_row[0]) if commission_row else 10.0

    return jsonify({
        "settings": {
            "commission_percent": commission_percent,
        },
        "stats": {
            "users": len(users),
            "jobs": len(jobs),
            "active_jobs": sum(1 for j in jobs if str(j[5]).lower() == "active"),
            "finished_jobs": sum(1 for j in jobs if str(j[5]).lower() == "finished"),
            "services": len(services),
            "ratings": len(ratings),
            "reports": len(reports),
        },
        "users": rows(users, ["id", "username", "first_name", "last_name", "email", "birthday", "bio", "skills", "role", "created_at", "average_rating", "balance"]),
        "jobs": rows(jobs, ["id", "title", "price", "currency", "location", "status", "created_at", "creator_username", "worker_username"]),
        "services": rows(services, ["id", "name", "parent_id", "parent_name", "created_by"]),
        "ratings": rows(ratings, ["id", "job_id", "score", "comment", "created_at", "from_username", "to_username"]),
        "reports": rows(reports, ["id", "reason", "details", "status", "created_at", "reporter_username", "reported_username"]),
    })


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

    return jsonify({"msg": "Foydalanuvchi ma'lumotlari yangilandi."})


@app.route("/admin/user/<int:user_id>", methods=["DELETE"])
@admin_required
def admin_delete_user(user_id):
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

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM messages WHERE sender_id=? OR receiver_id=?", (user_id, user_id))
        cur.execute("DELETE FROM ratings WHERE from_user=? OR to_user=?", (user_id, user_id))
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

    return jsonify({"msg": "Foydalanuvchi va unga bog'liq ma'lumotlar o'chirildi."})


@app.route("/admin/job/<int:job_id>", methods=["PATCH"])
@admin_required
def admin_update_job(job_id):
    d = request.json or {}
    status = str(d.get("status", "")).strip().lower()
    allowed = {"active", "payment_pending", "accepted", "pending_finish", "finished", "blocked"}

    if status not in allowed:
        return jsonify({"msg": "Ish holati noto‘g‘ri."}), 400

    job = db.q("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi."}), 404

    job_state = db.q("SELECT worker_id FROM jobs WHERE id=?", (job_id,)).fetchone()
    worker_id = job_state[0] if job_state else None
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

    return jsonify({"msg": "Ish holati yangilandi."})


@app.route("/admin/job/<int:job_id>", methods=["DELETE"])
@admin_required
def admin_delete_job(job_id):
    job = db.q("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi."}), 404

    held_payment = db.q("SELECT id FROM payments WHERE job_id=? AND status='held' LIMIT 1", (job_id,)).fetchone()
    if held_payment:
        return jsonify({"msg": "Bu ishda waiting to‘lovi bor. Avval refund qiling yoki shikoyatni admin orqali hal qiling."}), 409

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM messages WHERE job_id=?", (job_id,))
        cur.execute("DELETE FROM ratings WHERE job_id=?", (job_id,))
        cur.execute("DELETE FROM job_services WHERE job_id=?", (job_id,))
        cur.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

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

    return jsonify({"msg": "Xizmat qo‘shildi.", "id": new_id}), 201


@app.route("/admin/service/<int:service_id>", methods=["DELETE"])
@admin_required
def admin_delete_service(service_id):
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