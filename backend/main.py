import os
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
from payments import register_payment_routes
import jwt

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
allowed_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174").split(",")
CORS(app, resources={r"/*": {"origins": [origin.strip() for origin in allowed_origins if origin.strip()]}})
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=()"
    return response

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
                avatar_url TEXT DEFAULT ''
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
                custom_service TEXT DEFAULT ''
            )
        """)

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
                sent_at TEXT
            )
        """)

        # Database Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_status ON jobs(user_id, status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_worker_status ON jobs(worker_id, status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_service ON jobs(service_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_job ON messages(job_id, sent_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ratings_to_user ON ratings(to_user);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ratings_job ON ratings(job_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status, created_at);")

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
        if "created_at" not in existing_rating_cols:
            try:
                cursor.execute("ALTER TABLE ratings ADD COLUMN created_at TEXT")
            except Exception:
                pass

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
def token(uid, role="user"):
    return jwt.encode(
        {
            "id": uid,
            "role": role,
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7),
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
            d = jwt.decode(parts[1], app.config["SECRET_KEY"], algorithms=["HS256"])
            request.uid = d["id"]
            request.user_role = d.get("role", "user")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError):
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


register_payment_routes(app, db, auth, create_notification)

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

    if job_status not in ("accepted", "pending_finish", "finished"):
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
                db.q(
                    "UPDATE jobs SET status='blocked', finished_at=NULL WHERE id=?",
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
        """SELECT id, username, first_name, last_name, email, birthday, bio, skills, role, created_at, average_rating
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

    return jsonify({
        "stats": {
            "users": len(users),
            "jobs": len(jobs),
            "active_jobs": sum(1 for j in jobs if str(j[5]).lower() == "active"),
            "finished_jobs": sum(1 for j in jobs if str(j[5]).lower() == "finished"),
            "services": len(services),
            "ratings": len(ratings),
            "reports": len(reports),
        },
        "users": rows(users, ["id", "username", "first_name", "last_name", "email", "birthday", "bio", "skills", "role", "created_at", "average_rating"]),
        "jobs": rows(jobs, ["id", "title", "price", "currency", "location", "status", "created_at", "creator_username", "worker_username"]),
        "services": rows(services, ["id", "name", "parent_id", "parent_name", "created_by"]),
        "ratings": rows(ratings, ["id", "job_id", "score", "comment", "created_at", "from_username", "to_username"]),
        "reports": rows(reports, ["id", "reason", "details", "status", "created_at", "reporter_username", "reported_username"]),
    })


@app.route("/admin/user-role", methods=["PATCH"])
@admin_required
def admin_user_role():
    d = request.json or {}
    user_id = d.get("user_id")
    role = str(d.get("role", "")).strip().lower()

    if not user_id or role not in ("user", "admin"):
        return jsonify({"msg": "Foydalanuvchi ID raqami va roli to‘g‘ri ko‘rsatilishi kerak."}), 400

    if int(user_id) == int(request.uid):
        return jsonify({"msg": "Bu yerdan o‘zingizning administrator rolingizni o‘zgartira olmaysiz."}), 400

    target = db.q("SELECT id, role FROM users WHERE id=?", (user_id,)).fetchone()
    if not target:
        return jsonify({"msg": "Foydalanuvchi topilmadi."}), 404

    db.q("UPDATE users SET role=? WHERE id=?", (role, user_id)).close()
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

    duplicate = db.q(
        """SELECT id FROM users
           WHERE (username=? OR email=?) AND id!=?""",
        (username, email, user_id)
    ).fetchone()

    if duplicate:
        return jsonify({"msg": "Bu foydalanuvchi nomi yoki elektron pochta boshqa foydalanuvchida mavjud."}), 409

    if password:
        if len(password) < 8:
            return jsonify({"msg": "Yangi parol kamida 8 ta belgidan iborat bo'lishi kerak."}), 400

        hashed = generate_password_hash(password)
        db.q(
            """UPDATE users
               SET username=?, email=?, first_name=?, last_name=?, birthday=?,
                   bio=?, skills=?, password=?
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

    if status in {"payment_pending", "accepted", "pending_finish", "finished"} and not worker_id:
        return jsonify({"msg": "Bu holatni tanlash uchun avval ishga bajaruvchi biriktirilishi kerak."}), 400

    if status == "active":
        db.q("UPDATE jobs SET status='active', worker_id=NULL, finished_at=NULL WHERE id=?", (job_id,)).close()
    elif status == "payment_pending":
        db.q("UPDATE jobs SET status='payment_pending', finished_at=NULL WHERE id=?", (job_id,)).close()
    elif status == "accepted":
        db.q("UPDATE jobs SET status='accepted', finished_at=NULL WHERE id=?", (job_id,)).close()
    elif status == "pending_finish":
        db.q("UPDATE jobs SET status='pending_finish', finished_at=NULL WHERE id=?", (job_id,)).close()
    elif status == "blocked":
        db.q("UPDATE jobs SET status='blocked', finished_at=NULL WHERE id=?", (job_id,)).close()
    else:
        finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.q("UPDATE jobs SET status='finished', finished_at=? WHERE id=?", (finished_at, job_id)).close()

    return jsonify({"msg": "Ish holati yangilandi."})


@app.route("/admin/job/<int:job_id>", methods=["DELETE"])
@admin_required
def admin_delete_job(job_id):
    job = db.q("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi."}), 404

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
        return jsonify({"msg": "Bu xizmat mavjud joblarda ishlatilgan, o'chirib bo'lmaydi."}), 409

    db.q("DELETE FROM services WHERE id=?", (service_id,)).close()
    return jsonify({"msg": "Xizmat o‘chirildi."})


@app.route("/admin/rating/<int:rating_id>", methods=["DELETE"])
@admin_required
def admin_delete_rating(rating_id):
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

    return jsonify({"msg": "Baho o‘chirildi."})


# -------- AUTH --------
@app.route("/login", methods=["POST"])
def login():
    d = request.json or {}
    username_or_email = d.get("username", "").strip()
    password = d.get("password", "")

    if not username_or_email or not password:
        return jsonify({"msg": "Foydalanuvchi nomi/elektron pochta va parol kiritilishi shart!"}), 400

    if len(password) < 8:
        return jsonify({"msg": "Parol kamida 8 ta belgidan iborat bo‘lishi kerak"}), 400

    u = db.q(
        "SELECT id, password, role FROM users WHERE username=? OR email=?",
        (username_or_email, username_or_email),
    ).fetchone()
    if u and check_password_hash(u[1], password):
        user_role = u[2] if len(u) > 2 and u[2] else "user"
        return jsonify({"token": token(u[0], role=user_role), "role": user_role})
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

    if len(username) < 3 or len(username) > 32:
        return jsonify({"msg": "Foydalanuvchi nomi 3–32 belgidan iborat bo‘lishi kerak"}), 400

    if len(password) < 8:
        return jsonify({"msg": "Parol kamida 8 ta belgidan iborat bo‘lishi kerak"}), 400

    if len(email) > 254 or "@" not in email or email.startswith("@") or email.endswith("@"):
        return jsonify({"msg": "Elektron pochta manzili noto‘g‘ri"}), 400

    exists_u = db.q("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if exists_u:
        return jsonify({"msg": "Ushbu foydalanuvchi nomi allaqachon band!"}), 400

    exists_e = db.q("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if exists_e:
        return jsonify({"msg": "Ushbu elektron pochta allaqachon ro‘yxatdan o‘tgan!"}), 400

    code = str(secrets.randbelow(900000) + 100000)
    email_key = email
    pending_verifications[email_key] = {
        "code": code,
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

    email = d["email"].strip().lower()
    code = str(d["code"]).strip()

    if email not in pending_verifications:
        return jsonify({"msg": "Ushbu elektron pochta uchun tasdiqlash kodi so‘ralmagan yoki eskirgan!"}), 400

    record = pending_verifications[email]

    if datetime.datetime.now() > record["expiry"]:
        del pending_verifications[email]
        return jsonify({"msg": "Tasdiqlash kodining amal qilish muddati tugagan. Qaytadan so'rang."}), 400

    if not code.isdigit() or len(code) != 6 or record["code"] != code:
        return jsonify({"msg": "Tasdiqlash kodi noto'g'ri!"}), 400

    ud = record["data"]
    try:
        now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # First user can be registered as admin if table is empty
        count_users = db.q("SELECT COUNT(*) FROM users").fetchone()[0]
        assigned_role = "admin" if count_users == 0 else "user"

        db.q(
            """INSERT INTO users(username,password,first_name,last_name,birthday,email,bio,skills,created_at,average_rating,role)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
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
            ),
        )

        del pending_verifications[email]
        return jsonify({"msg": "ok", "role": assigned_role})
    except Exception:
        return jsonify({"msg": "Ro'yxatdan o'tishda xatolik yuz berdi"}), 400


@app.route("/logout", methods=["POST"])
def logout():
    return jsonify({"msg": "ok"})


# -------- SERVICES (ADMIN AUTHORIZATION REQUIRED) --------
@app.route("/services")
def get_services():
    r = db.q("SELECT id,name,parent_id FROM services").fetchall()
    return jsonify(rows(r, ["id", "name", "parent_id"]))


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

    custom_services = []
    seen_custom_services = set()

    for item in custom_service_values:
        custom_service = str(item).strip()
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

    if price <= 0 or price > 100000000000:
        return jsonify({"msg": "Narx 0 dan katta va 100 000 000 000 dan oshmasligi kerak"}), 400

    if currency not in {"UZS", "USD", "EUR"}:
        return jsonify({"msg": "Valyuta noto‘g‘ri tanlangan"}), 400

    primary_service_id = valid_service_ids[0] if valid_service_ids else None
    custom_service_text = ", ".join(custom_services)
    now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    insert_result = db.q(
        """INSERT INTO jobs(user_id,service_id,custom_service,title,description,price,location,worker_id,status,created_at,currency)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
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
    r = db.q(
        """
        SELECT j.id, j.title, j.price, j.currency, j.location, j.status, j.user_id, j.worker_id,
               u.first_name, u.last_name, u.username, j.description, j.service_id,
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
               j.created_at
        FROM jobs j
        LEFT JOIN users u ON j.worker_id = u.id
        LEFT JOIN services s ON j.service_id = s.id
        WHERE j.status = 'active'
           OR (
               j.status IN ('payment_pending', 'accepted', 'pending_finish', 'finished')
               AND (j.user_id = ? OR j.worker_id = ?)
           )
        ORDER BY j.id DESC
    """,
        (request.uid, request.uid),
    ).fetchall()

    return jsonify(
        rows(
            r,
            [
                "id",
                "title",
                "price",
                "currency",
                "location",
                "status",
                "user_id",
                "worker_id",
                "worker_first",
                "worker_last",
                "worker_username",
                "description",
                "service_id",
                "service_name",
                "created_at",
            ],
        )
    )


@app.route("/jobs/<int:job_id>")
@auth
def get_job_detail(job_id):
    r = db.q(
        """
        SELECT j.id, j.title, j.price, j.currency, j.location, j.status, j.user_id, j.worker_id,
               u.first_name, u.last_name, u.username, j.description, j.service_id,
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
        "service_name": r[13],
        "created_at": r[14],
        "creator_first": r[15],
        "creator_last": r[16],
        "creator_username": r[17],
    })


@app.route("/accept_job", methods=["POST"])
@auth
def accept():
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

    result = db.q(
        "UPDATE jobs SET worker_id=?,status='payment_pending' WHERE id=? AND status='active' AND worker_id IS NULL AND user_id!=?",
        (request.uid, job_id, request.uid),
    )
    updated = result.rowcount
    result.close()

    if updated != 1:
        return jsonify({"msg": "Ushbu ish allaqachon boshqa foydalanuvchi tomonidan qabul qilingan!"}), 409

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

    job = db.q("SELECT user_id, worker_id, status FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi"}), 404

    if job[0] != request.uid:
        return jsonify({"msg": "Faqat ish egasi bajaruvchini bekor qilishi mumkin"}), 403

    if job[1] is None:
        return jsonify({"msg": "Bu ishda hozir biriktirilgan bajaruvchi yo‘q"}), 400

    if job[2] not in ("payment_pending", "accepted"):
        return jsonify({"msg": "Bajaruvchini almashtirish faqat to‘lovdan oldin yoki qabul qilingan ishda mumkin"}), 400

    conn = db.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE jobs SET worker_id=NULL, status='active', finished_at=NULL WHERE id=? AND user_id=? AND status IN ('payment_pending','accepted')",
            (job_id, request.uid),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify({"msg": "Ish holati o‘zgardi. Qayta urinib ko‘ring"}), 409

        cursor.execute("DELETE FROM messages WHERE job_id=?", (job_id,))
        cursor.execute("DELETE FROM payments WHERE job_id=? AND status!='paid'", (job_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        return jsonify({"msg": "Bajaruvchini bekor qilishda xatolik yuz berdi"}), 500
    finally:
        conn.close()

    return jsonify({"msg": "ok", "status": "active"})


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

    job = db.q("SELECT user_id, worker_id, status FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi"}), 404
    if job[0] != request.uid:
        return jsonify({"msg": "Faqat ish yaratuvchisi yakunlash so'rovini yuborishi mumkin!"}), 403
    if not job[1]:
        return jsonify({"msg": "Ishni yakunlashdan oldin bajaruvchi tanlanishi kerak"}), 400
    if job[2] != "accepted":
        return jsonify({"msg": "Ish faqat to‘lov amalga oshirilgandan keyin yakunlanishi mumkin"}), 400

    result = db.q("UPDATE jobs SET status='pending_finish' WHERE id=?", (job_id,))
    result.close()
    return jsonify({"msg": "ok"})


@app.route("/confirm_finish", methods=["POST"])
@auth
def confirm_finish():
    d = request.json or {}
    job_id = d.get("job_id")
    choice = d.get("choice")

    if not job_id:
        return jsonify({"msg": "Ish identifikatori ko‘rsatilmagan"}), 400

    try:
        job_id = int(job_id)
    except (TypeError, ValueError):
        return jsonify({"msg": "Ish identifikatori noto‘g‘ri"}), 400

    job = db.q("SELECT user_id, worker_id, status, title FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi"}), 404
    if job[1] != request.uid:
        return jsonify({"msg": "Ruxsat berilmadi"}), 403
    if job[2] != "pending_finish":
        return jsonify({"msg": "Bu ish hozir tasdiqlashni kutmayapti"}), 400
    if choice not in ("yes", "no"):
        return jsonify({"msg": "Tanlov faqat ha yoki yo‘q bo‘lishi mumkin"}), 400

    if choice == "yes":
        now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result = db.q("UPDATE jobs SET status='finished', finished_at=? WHERE id=?", (now_time, job_id))
        result.close()
        create_notification(
            job[0],
            "job_finished",
            "Ishingiz yakunlandi",
            f"Sizning «{job[3]}» nomli ishingiz ishchi tomonidan yakunlandi.",
            "/jobs",
        )
        return jsonify({"msg": "ok", "status": "finished"})

    result = db.q(
        "UPDATE jobs SET status='accepted' WHERE id=? AND status='pending_finish' AND user_id=?",
        (job_id, request.uid),
    )
    updated = result.rowcount
    result.close()
    if updated != 1:
        return jsonify({"msg": "Ish holati o‘zgardi. Qayta urinib ko‘ring"}), 409
    return jsonify({"msg": "rejected", "status": "accepted"})


# -------- MESSAGES --------
@app.route("/message", methods=["POST"])
@auth
def msg():
    d = request.json or {}
    job_id = d.get("job_id")
    message_text = d.get("message", "").strip()

    if not job_id or not message_text:
        return jsonify({"msg": "Ish identifikatori va xabar maydonlari talab qilinadi"}), 400

    if len(message_text) > 5000:
        return jsonify({"msg": "Xabar 5000 belgidan oshmasligi kerak"}), 400

    job = db.q("SELECT user_id, worker_id, status FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi"}), 404

    if request.uid == job[0]:
        receiver_id = job[1]
    elif request.uid == job[1]:
        receiver_id = job[0]
    else:
        return jsonify({"msg": "Siz bu ishga aloqador emassiz"}), 403

    if not receiver_id:
        return jsonify({"msg": "Bu ishni hali hech kim qabul qilmagan"}), 400

    clean_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.q(
        "INSERT INTO messages(sender_id,receiver_id,job_id,message,sent_at) VALUES(?,?,?,?,?)",
        (request.uid, receiver_id, job_id, message_text, clean_now),
    )
    return jsonify({"msg": "ok"})


@app.route("/messages/<int:job_id>")
@auth
def get_msg(job_id):
    job = db.q("SELECT user_id, worker_id FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Ish topilmadi"}), 404
    if request.uid != job[0] and request.uid != job[1]:
        return jsonify({"msg": "Ruxsat berilmadi"}), 403

    r = db.q(
        """SELECT u.first_name, u.last_name, m.message, m.sent_at, u.username, m.sender_id 
           FROM messages m 
           LEFT JOIN users u ON m.sender_id = u.id 
           WHERE m.job_id=? 
           ORDER BY m.id ASC""",
        (job_id,),
    ).fetchall()
    return jsonify([
        {
            "sender_name": f"{i[0]} {i[1]}".strip() if (i[0] or i[1]) else i[4],
            "message": i[2],
            "sent_at": i[3].split(".")[0] if i[3] else "",
            "sender_id": i[5],
        }
        for i in r
    ])


# -------- RATINGS --------
@app.route("/rating", methods=["POST"])
@auth
def add_rating():
    d = request.json or {}
    job_id = d.get("job_id")
    to_user = d.get("to_user")
    score = d.get("score")
    comment = d.get("comment", "").strip()

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
    result = db.q(
        "INSERT INTO ratings(job_id, from_user, to_user, score, comment, created_at) VALUES(?,?,?,?,?,?)",
        (job_id, request.uid, to_user, score, comment, now_time),
    )
    result.close()

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
        {"id": i[0], "name": f"{i[1]} {i[2]}".strip() if (i[1] or i[2]) else i[3], "count": i[4]}
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
        {"id": i[0], "name": f"{i[1]} {i[2]}".strip() if (i[1] or i[2]) else i[3], "count": i[4]}
        for i in workers_raw
    ]

    return jsonify({"creators": creators, "workers": workers})


# -------- PROFILE PHOTO --------
PROFILE_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "profile_pictures")
os.makedirs(PROFILE_UPLOAD_DIR, exist_ok=True)
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_PROFILE_IMAGE_SIZE = 5 * 1024 * 1024


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

    filename = f"{request.uid}_{uuid.uuid4().hex}.{extension}"
    filepath = os.path.join(PROFILE_UPLOAD_DIR, filename)
    image.save(filepath)

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


# -------- PROFILE --------
@app.route("/profile", methods=["GET", "PUT"])
@auth
def profile():
    if request.method == "GET":
        u = db.q(
            "SELECT id, username, first_name, last_name, email, birthday, bio, skills, created_at, average_rating, role, avatar_url FROM users WHERE id=?",
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
        })

    elif request.method == "PUT":
        d = request.json or {}
        username = d.get("username", "").strip()
        email = d.get("email", "").strip().lower()

        if not username or not email:
            return jsonify({"msg": "Foydalanuvchi nomi va elektron pochta kiritilishi shart"}), 400

        exists_u = db.q("SELECT id FROM users WHERE username=? AND id!=?", (username, request.uid)).fetchone()
        if exists_u:
            return jsonify({"msg": "Ushbu foydalanuvchi nomi allaqachon band!"}), 400

        exists_e = db.q("SELECT id FROM users WHERE email=? AND id!=?", (email, request.uid)).fetchone()
        if exists_e:
            return jsonify({"msg": "Ushbu elektron pochta allaqachon ro‘yxatdan o‘tgan!"}), 400

        result = db.q(
            """UPDATE users 
               SET first_name=?, last_name=?, birthday=?, username=?, email=?, bio=?, skills=? 
               WHERE id=?""",
            (
                d.get("first_name", "").strip(),
                d.get("last_name", "").strip(),
                d.get("birthday", "").strip(),
                username,
                email,
                d.get("bio", "").strip(),
                d.get("skills", "").strip(),
                request.uid,
            ),
        )
        result.close()

        return jsonify({"msg": "ok"})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
