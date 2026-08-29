import os
import sqlite3
import datetime
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import jwt

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
CORS(app)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "super_secret_jwt_key_job_platform_secure_32_bytes")

# -------- E-MAIL (SMTP) SOZLAMALARI --------
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "xudayberganovallanazar5@gmail.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "rvxxnpqochnuhanw")

# Vaqtinchalik tasdiqlash kodlarini xotirada saqlash uchun lug'at:
# email -> { "code": str, "data": dict, "expiry": datetime }
pending_verifications = {}


def send_email_code(to_email, code):
    subject = "Job Platform - Ro'yxatdan o'tish kodi"
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
        print("\n" + "=" * 50)
        print(f"!!! EMAIL YUBORISHDA XATO !!!: {e}")
        print(f"!!! DIQQAT! TASDIQLASH KODI TERMINALDA !!!")
        print(f"Email: {to_email}")
        print(f"TASDIQLASH KODI: {code}")
        print("=" * 50 + "\n")
        return True


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
                role TEXT DEFAULT 'user'
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
                location TEXT,
                worker_id INTEGER,
                status TEXT,
                created_at TEXT,
                finished_at TEXT
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

        # Dynamic migrations for any existing tables missing new columns
        cursor.execute("PRAGMA table_info(users)")
        existing_user_cols = [row[1] for row in cursor.fetchall()]
        migrations = [
            ("bio", "ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''"),
            ("skills", "ALTER TABLE users ADD COLUMN skills TEXT DEFAULT ''"),
            ("created_at", "ALTER TABLE users ADD COLUMN created_at TEXT"),
            ("average_rating", "ALTER TABLE users ADD COLUMN average_rating REAL DEFAULT 0.0"),
            ("role", "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'"),
        ]
        for col_name, sql in migrations:
            if col_name not in existing_user_cols:
                try:
                    cursor.execute(sql)
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

        cursor.execute("SELECT COUNT(*) FROM services")
        r = cursor.fetchone()[0]
        if r > 0:
            conn.close()
            return

        cursor.execute("INSERT INTO services(name,parent_id,created_by) VALUES('Ustalar',NULL,1)")
        cursor.execute("INSERT INTO services(name,parent_id,created_by) VALUES('IT xizmatlar',NULL,1)")
        cursor.execute("INSERT INTO services(name,parent_id,created_by) VALUES('Uy ishlari',NULL,1)")

        cursor.execute("SELECT id FROM services WHERE name='Ustalar'")
        u = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM services WHERE name='IT xizmatlar'")
        it = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM services WHERE name='Uy ishlari'")
        uy = cursor.fetchone()[0]

        cursor.execute("INSERT INTO services(name,parent_id,created_by) VALUES('Santexnik',?,1)", (u,))
        cursor.execute("INSERT INTO services(name,parent_id,created_by) VALUES('Elektrik',?,1)", (u,))
        cursor.execute("INSERT INTO services(name,parent_id,created_by) VALUES(?,?,1)", ("Ta'mirlash", u))
        cursor.execute("INSERT INTO services(name,parent_id,created_by) VALUES('Web dasturlash',?,1)", (it,))
        cursor.execute("INSERT INTO services(name,parent_id,created_by) VALUES('Telegram bot',?,1)", (it,))
        cursor.execute("INSERT INTO services(name,parent_id,created_by) VALUES('Mobil ilova',?,1)", (it,))
        cursor.execute("INSERT INTO services(name,parent_id,created_by) VALUES('Tozalash',?,1)", (uy,))
        cursor.execute("INSERT INTO services(name,parent_id,created_by) VALUES('Ovqat pishirish',?,1)", (uy,))
        cursor.execute("INSERT INTO services(name,parent_id,created_by) VALUES('Bolaga qarash',?,1)", (uy,))
        conn.commit()
        conn.close()

    def q(self, sql, args=()):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, args)
        conn.commit()
        return cursor


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
        t = request.headers.get("Authorization")
        if not t:
            return jsonify({"msg": "no token"}), 401
        try:
            p = t.split()
            if len(p) < 2:
                return jsonify({"msg": "bad token"}), 401
            d = jwt.decode(p[1], app.config["SECRET_KEY"], algorithms=["HS256"])
            request.uid = d["id"]
            request.user_role = d.get("role", "user")
        except Exception as e:
            return jsonify({"msg": "invalid token", "error": str(e)}), 401
        return f(*a, **k)

    return w


def admin_required(f):
    @wraps(f)
    @auth
    def w(*a, **k):
        u = db.q("SELECT role FROM users WHERE id=?", (request.uid,)).fetchone()
        role = u[0] if u else "user"
        if role != "admin":
            return jsonify({"msg": "Ruxsat berilmadi: Faqat administratorlar uchun ruxsat etilgan!"}), 403
        return f(*a, **k)

    return w


def rows(r, cols):
    return [dict(zip(cols, i)) for i in r]


# -------- AUTH --------
@app.route("/login", methods=["POST"])
def login():
    d = request.json or {}
    username_or_email = d.get("username", "").strip()
    password = d.get("password", "")

    if not username_or_email or not password:
        return jsonify({"msg": "Username/Email va parol kiritilishi shart!"}), 400

    u = db.q(
        "SELECT id, password, role FROM users WHERE username=? OR email=?",
        (username_or_email, username_or_email),
    ).fetchone()
    if u and check_password_hash(u[1], password):
        user_role = u[2] if len(u) > 2 and u[2] else "user"
        return jsonify({"token": token(u[0], role=user_role), "role": user_role})
    return jsonify({"msg": "Username/Email yoki Parol xato!"}), 401


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

    exists_u = db.q("SELECT id FROM users WHERE username=?", (d["username"].strip(),)).fetchone()
    if exists_u:
        return jsonify({"msg": "Ushbu Username allaqachon band!"}), 400

    exists_e = db.q("SELECT id FROM users WHERE email=?", (d["email"].strip().lower(),)).fetchone()
    if exists_e:
        return jsonify({"msg": "Ushbu Email allaqachon ro'yxatdan o'tgan!"}), 400

    code = str(random.randint(100000, 999999))
    email_key = d["email"].strip().lower()
    pending_verifications[email_key] = {
        "code": code,
        "data": {**d, "email": email_key, "username": d["username"].strip()},
        "expiry": datetime.datetime.now() + datetime.timedelta(minutes=10),
    }

    send_email_code(email_key, code)
    return jsonify({"msg": "ok", "info": "Tasdiqlash kodi elektron pochtangizga yuborildi."})


# 2-QADAM: Kodni tasdiqlab ro'yxatdan o'tkazish
@app.route("/register/verify", methods=["POST"])
def verify_code():
    d = request.json
    if not d or "email" not in d or "code" not in d:
        return jsonify({"msg": "Email va tasdiqlash kodi talab qilinadi"}), 400

    email = d["email"].strip().lower()
    code = str(d["code"]).strip()

    if email not in pending_verifications:
        return jsonify({"msg": "Ushbu email uchun tasdiqlash kodi so'ralmagan yoki eskirgan!"}), 400

    record = pending_verifications[email]

    if datetime.datetime.now() > record["expiry"]:
        del pending_verifications[email]
        return jsonify({"msg": "Tasdiqlash kodining amal qilish muddati tugagan. Qaytadan so'rang."}), 400

    if record["code"] != code:
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
                generate_password_hash(ud["password"]),
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
    except Exception as e:
        return jsonify({"msg": f"Xatolik yuz berdi: {str(e)}"}), 400


@app.route("/logout", methods=["POST"])
def logout():
    return jsonify({"msg": "ok"})


# -------- SERVICES (ADMIN AUTHORIZATION REQUIRED) --------
@app.route("/service", methods=["POST"])
@admin_required
def add_service():
    d = request.json or {}
    name = d.get("name", "").strip()
    if not name:
        return jsonify({"msg": "Xizmat nomi kiritilishi shart"}), 400
    db.q("INSERT INTO services(name,parent_id,created_by) VALUES(?,?,?)", (name, d.get("parent_id"), request.uid))
    return jsonify({"msg": "ok"})


@app.route("/services")
def get_services():
    r = db.q("SELECT id,name,parent_id FROM services").fetchall()
    return jsonify(rows(r, ["id", "name", "parent_id"]))


# -------- JOBS --------
@app.route("/job", methods=["POST"])
@auth
def add_job():
    d = request.json or {}
    if not d.get("service_id") or not d.get("title") or not d.get("price") or not d.get("location"):
        return jsonify({"msg": "Barcha maydonlarni to'ldiring"}), 400

    now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.q(
        """INSERT INTO jobs(user_id,service_id,title,description,price,location,worker_id,status,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            request.uid,
            d["service_id"],
            d["title"].strip(),
            d.get("description", "").strip(),
            d["price"],
            d["location"].strip(),
            None,
            "active",
            now_time,
        ),
    )
    return jsonify({"msg": "ok"})


@app.route("/jobs")
@auth
def get_jobs():
    r = db.q(
        """
        SELECT j.id, j.title, j.price, j.location, j.status, j.user_id, j.worker_id,
               u.first_name, u.last_name, u.username, j.description, j.service_id, s.name as service_name
        FROM jobs j
        LEFT JOIN users u ON j.worker_id = u.id
        LEFT JOIN services s ON j.service_id = s.id
        WHERE j.status != 'finished' 
        AND (j.status = 'active' OR j.user_id = ? OR j.worker_id = ?)
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
            ],
        )
    )


@app.route("/jobs/<int:job_id>")
@auth
def get_job_detail(job_id):
    r = db.q(
        """
        SELECT j.id, j.title, j.price, j.location, j.status, j.user_id, j.worker_id,
               u.first_name, u.last_name, u.username, j.description, j.service_id, s.name as service_name,
               c.first_name as creator_first, c.last_name as creator_last, c.username as creator_username
        FROM jobs j
        LEFT JOIN users u ON j.worker_id = u.id
        LEFT JOIN users c ON j.user_id = c.id
        LEFT JOIN services s ON j.service_id = s.id
        WHERE j.id = ?
    """,
        (job_id,),
    ).fetchone()
    if not r:
        return jsonify({"msg": "Job topilmadi"}), 404
    return jsonify({
        "id": r[0],
        "title": r[1],
        "price": r[2],
        "location": r[3],
        "status": r[4],
        "user_id": r[5],
        "worker_id": r[6],
        "worker_first": r[7],
        "worker_last": r[8],
        "worker_username": r[9],
        "description": r[10],
        "service_id": r[11],
        "service_name": r[12],
        "creator_first": r[13],
        "creator_last": r[14],
        "creator_username": r[15],
    })


@app.route("/accept_job", methods=["POST"])
@auth
def accept():
    d = request.json or {}
    job_id = d.get("job_id")
    if not job_id:
        return jsonify({"msg": "job_id ko'rsatilmadi"}), 400

    job = db.q("SELECT user_id, status, worker_id FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Job topilmadi"}), 404
    if job[0] == request.uid:
        return jsonify({"msg": "O'zingiz yaratgan ishni qabul qila olmaysiz!"}), 400
    if job[1] != "active" or job[2] is not None:
        return jsonify({"msg": "Ushbu ish allaqachon boshqa foydalanuvchi tomonidan qabul qilingan!"}), 400

    db.q("UPDATE jobs SET worker_id=?,status='accepted' WHERE id=?", (request.uid, job_id))
    return jsonify({"msg": "ok"})


@app.route("/finish_job", methods=["POST"])
@auth
def finish():
    d = request.json or {}
    job_id = d.get("job_id")
    if not job_id:
        return jsonify({"msg": "job_id ko'rsatilmadi"}), 400

    job = db.q("SELECT user_id, worker_id, status FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Job topilmadi"}), 404
    if job[0] != request.uid:
        return jsonify({"msg": "Faqat ish yaratuvchisi yakunlash so'rovini yuborishi mumkin!"}), 403
    if job[2] != "accepted":
        return jsonify({"msg": "Ish faqat qabul qilingan holatda yakunlanishi mumkin"}), 400

    db.q("UPDATE jobs SET status='pending_finish' WHERE id=?", (job_id,))
    return jsonify({"msg": "ok"})


@app.route("/confirm_finish", methods=["POST"])
@auth
def confirm_finish():
    d = request.json or {}
    job_id = d.get("job_id")
    choice = d.get("choice")

    job = db.q("SELECT worker_id, status FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Job topilmadi"}), 404
    if job[0] != request.uid:
        return jsonify({"msg": "Ruxsat berilmadi"}), 403

    if choice == "yes":
        now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.q("UPDATE jobs SET status='finished', finished_at=? WHERE id=?", (now_time, job_id))
        return jsonify({"msg": "ok", "status": "finished"})
    else:
        db.q("UPDATE jobs SET status='accepted' WHERE id=?", (job_id,))
        return jsonify({"msg": "rejected", "status": "accepted"})


# -------- MESSAGES --------
@app.route("/message", methods=["POST"])
@auth
def msg():
    d = request.json or {}
    job_id = d.get("job_id")
    message_text = d.get("message", "").strip()

    if not job_id or not message_text:
        return jsonify({"msg": "job_id va message maydonlari talab qilinadi"}), 400

    job = db.q("SELECT user_id, worker_id FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Job topilmadi"}), 404

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
        return jsonify({"msg": "Job topilmadi"}), 404
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
        return jsonify({"msg": "job_id, to_user va score to'ldirilishi shart"}), 400

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

    job = db.q("SELECT user_id, worker_id FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"msg": "Job topilmadi"}), 404

    if request.uid != job[0] and request.uid != job[1]:
        return jsonify({"msg": "Siz ushbu ish ishtirokchisi emassiz"}), 403

    now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.q(
        "INSERT INTO ratings(job_id, from_user, to_user, score, comment, created_at) VALUES(?,?,?,?,?,?)",
        (job_id, request.uid, to_user, score, comment, now_time),
    )

    avg_row = db.q("SELECT AVG(score) FROM ratings WHERE to_user=?", (to_user,)).fetchone()
    avg_score = round(avg_row[0], 1) if avg_row and avg_row[0] is not None else 0.0
    db.q("UPDATE users SET average_rating=? WHERE id=?", (avg_score, to_user))

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


# -------- PROFILE --------
@app.route("/profile", methods=["GET", "PUT"])
@auth
def profile():
    if request.method == "GET":
        u = db.q(
            "SELECT id, username, first_name, last_name, email, birthday, bio, skills, created_at, average_rating, role FROM users WHERE id=?",
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
        })

    elif request.method == "PUT":
        d = request.json or {}
        username = d.get("username", "").strip()
        email = d.get("email", "").strip().lower()

        if not username or not email:
            return jsonify({"msg": "Username va email kiritilishi shart"}), 400

        exists_u = db.q("SELECT id FROM users WHERE username=? AND id!=?", (username, request.uid)).fetchone()
        if exists_u:
            return jsonify({"msg": "Ushbu Username allaqachon band!"}), 400

        exists_e = db.q("SELECT id FROM users WHERE email=? AND id!=?", (email, request.uid)).fetchone()
        if exists_e:
            return jsonify({"msg": "Ushbu Email allaqachon ro'yxatdan o'tgan!"}), 400

        db.q(
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

        return jsonify({"msg": "ok"})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
