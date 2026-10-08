import datetime
import hashlib
import json
import os
import math
import secrets
import uuid
from urllib.parse import urlencode
from flask import jsonify, request


CLICK_SERVICE_ID = os.environ.get("CLICK_SERVICE_ID", "").strip()
CLICK_MERCHANT_ID = os.environ.get("CLICK_MERCHANT_ID", "").strip()
CLICK_SECRET_KEY = os.environ.get("CLICK_SECRET_KEY", "").strip()
CLICK_RETURN_URL = os.environ.get("CLICK_RETURN_URL", "http://localhost:5173/jobs").strip()
CLICK_CHECKOUT_URL = "https://my.click.uz/services/pay"


def register_payment_routes(app, db, auth, admin_required, create_notification, admin_audit=None, enforce_block=None):
    def click_signature(click_trans_id, service_id, secret_key, merchant_trans_id, amount, action, sign_time):
        raw = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{amount}{action}{sign_time}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def click_error(code, note):
        return jsonify({"error": code, "error_note": note})

    def build_checkout_url(payment_uuid, amount):
        params = {
            "service_id": CLICK_SERVICE_ID,
            "merchant_id": CLICK_MERCHANT_ID,
            "amount": f"{float(amount):.2f}",
            "transaction_param": payment_uuid,
            "return_url": CLICK_RETURN_URL,
        }
        return CLICK_CHECKOUT_URL + "?" + urlencode(params)

    def ensure_table():
        conn = db.get_connection()
        try:
            conn.execute("""
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_payer_status ON payments(payer_id,status,created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_payee_status ON payments(payee_id,status,created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_job_status ON payments(job_id,status)")
            conn.commit()
        finally:
            conn.close()

    ensure_table()
    conn = db.get_connection()
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "balance" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0")
        conn.execute("""CREATE TABLE IF NOT EXISTS wallet_transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            balance_after REAL NOT NULL,
            job_id INTEGER,
            description TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS platform_wallet(
            id INTEGER PRIMARY KEY CHECK(id=1),
            balance REAL NOT NULL DEFAULT 0,
            escrow_balance REAL NOT NULL DEFAULT 0
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS platform_settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")
        conn.execute(
            "INSERT OR IGNORE INTO platform_settings(key,value) VALUES('commission_percent','10')"
        )
        platform_columns = [row[1] for row in conn.execute("PRAGMA table_info(platform_wallet)").fetchall()]
        if "escrow_balance" not in platform_columns:
            conn.execute("ALTER TABLE platform_wallet ADD COLUMN escrow_balance REAL NOT NULL DEFAULT 0")
        conn.execute("INSERT OR IGNORE INTO platform_wallet(id,balance,escrow_balance) VALUES(1,0,0)")
        conn.execute(
            "UPDATE payments SET status='released',released_at=COALESCE(released_at,paid_at) WHERE provider='dummy' AND status='paid' AND released_at IS NULL"
        )
        conn.commit()
    finally:
        conn.close()

    def _commission_preview(amount):
        amount = float(amount)
        commission_percent = _commission_percent()
        commission = round(amount * commission_percent / 100, 2)
        worker_amount = round(amount - commission, 2)
        return commission_percent, commission, worker_amount

    @app.route("/payments/config")
    @auth
    def payment_config():
        return jsonify({
            "click_enabled": bool(CLICK_SERVICE_ID and CLICK_MERCHANT_ID and CLICK_SECRET_KEY),
            "providers": ["click"] if CLICK_SERVICE_ID and CLICK_MERCHANT_ID and CLICK_SECRET_KEY else [],
            "commission_percent": _commission_percent(),
        })

    @app.route("/payments/job/<int:job_id>")
    @auth
    def get_job_payment_access(job_id):
        job = db.q(
            """SELECT user_id,worker_id,status,COALESCE(agreed_price,price),currency,title
               FROM jobs WHERE id=?""",
            (job_id,),
        ).fetchone()
        if not job:
            return jsonify({"msg": "To‘lov topilmadi"}), 404

        owner_id, worker_id, job_status, price, currency, title = job
        payment = db.q(
            """SELECT payment_uuid,amount,currency,provider,status,paid_at,created_at
               FROM payments WHERE job_id=? ORDER BY id DESC LIMIT 1""",
            (job_id,),
        ).fetchone()

        is_participant = request.uid in (owner_id, worker_id)
        if not is_participant:
            return jsonify({"msg": "To‘lov topilmadi"}), 404

        if payment:
            return jsonify({
                "ok": True,
                "payment_uuid": payment[0],
                "job_id": job_id,
                "amount": payment[1],
                "currency": payment[2],
                "provider": payment[3],
                "status": payment[4],
                "paid_at": payment[5],
                "created_at": payment[6],
                "title": title,
            })

        if request.uid == owner_id and job_status == "payment_pending" and worker_id:
            return jsonify({
                "ok": True,
                "payment_ready": True,
                "job_id": job_id,
                "amount": float(price),
                "currency": currency or "UZS",
                "title": title,
            })

        return jsonify({"msg": "To‘lov topilmadi"}), 404


    @app.route("/payments/create/<int:job_id>", methods=["POST"])
    @auth
    def create_payment(job_id):
        job = db.q(
            "SELECT user_id,worker_id,status,COALESCE(agreed_price,price),currency,title FROM jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if not job:
            return jsonify({"msg": "Ish topilmadi"}), 404

        owner_id, worker_id, job_status, price, currency, title = job
        if owner_id != request.uid:
            return jsonify({"msg": "To‘lovni faqat ish egasi amalga oshirishi mumkin"}), 403
        if job_status != "payment_pending" or not worker_id:
            return jsonify({"msg": "Bu ish hozir to‘lov uchun tayyor emas"}), 400
        if str(currency).upper() != "UZS":
            return jsonify({"msg": "Click orqali hozircha faqat UZS to‘lovlari qabul qilinadi"}), 400
        if not CLICK_SERVICE_ID or not CLICK_MERCHANT_ID or not CLICK_SECRET_KEY:
            existing = db.q(
                "SELECT payment_uuid,amount,currency,status FROM payments WHERE job_id=? AND provider='dummy'",
                (job_id,),
            ).fetchone()
            if existing:
                return jsonify({
                    "msg": "ok",
                    "status": existing[3],
                    "payment_uuid": existing[0],
                    "amount": existing[1],
                    "currency": existing[2],
                    "provider": "dummy",
                    "title": title,
                    "commission_percent": _commission_preview(existing[1])[0],
                    "commission_amount": _commission_preview(existing[1])[1],
                    "worker_amount": _commission_preview(existing[1])[2],
                })
            payment_uuid = str(uuid.uuid4())
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            result = db.q(
                """INSERT INTO payments(
                    payment_uuid,job_id,payer_id,payee_id,amount,currency,provider,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (payment_uuid,job_id,owner_id,worker_id,float(price),"UZS","dummy","pending",now),
            )
            result.close()
            return jsonify({
                "msg": "ok",
                "status": "pending",
                "payment_uuid": payment_uuid,
                "amount": float(price),
                "currency": "UZS",
                "provider": "dummy",
                "title": title,
                "commission_percent": _commission_preview(float(price))[0],
                "commission_amount": _commission_preview(float(price))[1],
                "worker_amount": _commission_preview(float(price))[2],
            })

        existing = db.q(
            "SELECT payment_uuid,amount,currency,status FROM payments WHERE job_id=? AND provider='click'",
            (job_id,),
        ).fetchone()

        if existing:
            payment_uuid, amount, payment_currency, payment_status = existing
            if payment_status == "paid":
                return jsonify({"msg": "already_paid", "status": "paid"})
            return jsonify({
                "msg": "ok",
                "status": payment_status,
                "payment_uuid": payment_uuid,
                "amount": amount,
                "currency": payment_currency,
                "checkout_url": build_checkout_url(payment_uuid, amount),
                "title": title,
                "commission_percent": _commission_preview(amount)[0],
                "commission_amount": _commission_preview(amount)[1],
                "worker_amount": _commission_preview(amount)[2],
            })

        payment_uuid = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result = db.q(
            """INSERT INTO payments(
                payment_uuid,job_id,payer_id,payee_id,amount,currency,provider,status,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (payment_uuid,job_id,owner_id,worker_id,float(price),"UZS","click","pending",now),
        )
        result.close()

        return jsonify({
            "msg": "ok",
            "status": "pending",
            "payment_uuid": payment_uuid,
            "amount": float(price),
            "currency": "UZS",
            "checkout_url": build_checkout_url(payment_uuid, price),
            "title": title,
            "commission_percent": _commission_preview(float(price))[0],
            "commission_amount": _commission_preview(float(price))[1],
            "worker_amount": _commission_preview(float(price))[2],
        })

    @app.route("/payments/<payment_uuid>")
    @auth
    def get_payment(payment_uuid):
        payment = db.q(
            """SELECT p.payment_uuid,p.job_id,p.payer_id,p.payee_id,p.amount,p.currency,
                      p.provider,p.status,p.provider_transaction_id,p.created_at,p.paid_at,j.title
               FROM payments p JOIN jobs j ON j.id=p.job_id
               WHERE p.payment_uuid=?""",
            (payment_uuid,),
        ).fetchone()
        if not payment:
            return jsonify({"msg": "To‘lov topilmadi"}), 404
        current_job = db.q("SELECT user_id,worker_id FROM jobs WHERE id=?", (payment[1],)).fetchone()
        if not current_job or request.uid not in (current_job[0], current_job[1]):
            return jsonify({"msg": "Ruxsat berilmadi"}), 403

        return jsonify({
            "payment_uuid": payment[0],
            "job_id": payment[1],
            "payer_id": payment[2],
            "payee_id": payment[3],
            "amount": payment[4],
            "currency": payment[5],
            "provider": payment[6],
            "status": payment[7],
            "provider_transaction_id": payment[8],
            "created_at": payment[9],
            "paid_at": payment[10],
            "title": payment[11],
            "commission_percent": _commission_preview(payment[4])[0],
            "commission_amount": _commission_preview(payment[4])[1],
            "worker_amount": _commission_preview(payment[4])[2],
        })

    @app.route("/payments")
    @auth
    def list_payments():
        items = db.q(
            """SELECT p.payment_uuid,p.job_id,p.amount,p.currency,p.provider,p.status,
                      p.created_at,p.paid_at,j.title,pu.username,ru.username
               FROM payments p
               JOIN jobs j ON j.id=p.job_id
               LEFT JOIN users pu ON pu.id=p.payer_id
               LEFT JOIN users ru ON ru.id=p.payee_id
               WHERE p.payer_id=? OR j.worker_id=?
               ORDER BY p.id DESC LIMIT 100""",
            (request.uid,request.uid),
        ).fetchall()
        return jsonify([
            {
                "payment_uuid": x[0], "job_id": x[1], "amount": x[2],
                "currency": x[3], "provider": x[4], "status": x[5],
                "created_at": x[6], "paid_at": x[7], "title": x[8],
                "payer_username": x[9], "payee_username": x[10]
            }
            for x in items
        ])


    def _wallet_tx(cur, user_id, tx_type, amount, balance_after, job_id, description, now):
        cur.execute(
            """INSERT INTO wallet_transactions
               (user_id,type,amount,balance_after,job_id,description,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (user_id, tx_type, amount, balance_after, job_id, description, now),
        )

    def _commission_percent():
        try:
            row = db.q("SELECT value FROM platform_settings WHERE key='commission_percent'").fetchone()
            value = float(row[0]) if row else 10
        except (TypeError, ValueError):
            value = 10
        return max(0, min(100, value))

    def release_payment(job_id):
        job = db.q("SELECT user_id,worker_id,status,COALESCE(agreed_price,price),title FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job or not job[1]:
            return False, "Ish yoki bajaruvchi topilmadi", None
        payment = db.q(
            """SELECT id,payment_uuid,payer_id,payee_id,amount,status
               FROM payments WHERE job_id=? ORDER BY id DESC LIMIT 1""",
            (job_id,),
        ).fetchone()
        if not payment:
            return False, "Bu ish uchun to‘lov topilmadi", None
        payment_id,payment_uuid,payer_id,payee_id,amount,status = payment
        if status == "released":
            return True, "already_released", {"amount": float(amount)}
        if status != "held":
            return False, "To‘lov hali waiting holatida emas", None
        if payee_id != job[1]:
            return False, "To‘lovning bajaruvchisi ishdagi hozirgi bajaruvchi bilan mos emas", None

        amount = float(amount)
        commission = round(amount * _commission_percent() / 100, 2)
        worker_amount = round(amount - commission, 2)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE platform_wallet SET escrow_balance=ROUND(escrow_balance-?,2) WHERE id=1 AND escrow_balance>=?",
                (amount, amount),
            )
            if cur.rowcount != 1:
                raise ValueError("escrow_insufficient")
            cur.execute(
                "UPDATE users SET balance=ROUND(COALESCE(balance,0)+?,2) WHERE id=?",
                (worker_amount, job[1]),
            )
            worker_after = cur.execute("SELECT COALESCE(balance,0) FROM users WHERE id=?", (job[1],)).fetchone()[0]
            cur.execute("UPDATE platform_wallet SET balance=ROUND(balance+?,2) WHERE id=1", (commission,))
            cur.execute(
                "UPDATE payments SET status='released',payee_id=?,released_at=?,provider_payload=? WHERE id=? AND status='held'",
                (job[1], now, json.dumps({"commission": commission, "worker_amount": worker_amount}, ensure_ascii=False), payment_id),
            )
            if cur.rowcount != 1:
                raise ValueError("payment_state_changed")
            _wallet_tx(cur, job[1], "payment_release", worker_amount, worker_after, job_id, f"«{job[4]}» ishidan yechilgan waiting to‘lovi", now)
            conn.commit()
        except Exception as e:
            conn.rollback()
            if str(e) == "escrow_insufficient":
                return False, "Escrow balansida mablag‘ yetarli emas", None
            if str(e) == "payment_state_changed":
                return False, "To‘lov holati o‘zgardi", None
            raise
        finally:
            conn.close()

        create_notification(payer_id, "payment_released", "To‘lov ishchiga o‘tkazildi",
            f"«{job[4]}» bo‘yicha {amount:,.0f} UZS waiting to‘lovi ish yakunlangani tasdiqlangach ishchiga o‘tkazildi.", "/payments")
        create_notification(job[1], "payment_received", "To‘lov balansingizga tushdi",
            f"«{job[4]}» bo‘yicha {worker_amount:,.0f} UZS daromad balansingizga o‘tkazildi.", "/payments")
        return True, "released", {"amount": amount, "commission": commission, "worker_amount": worker_amount}

    def refund_payment(job_id):
        job = db.q("SELECT user_id,worker_id,status,COALESCE(agreed_price,price),title FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return False, "Ish topilmadi", None
        payment = db.q(
            """SELECT id,payment_uuid,payer_id,payee_id,amount,status
               FROM payments WHERE job_id=? ORDER BY id DESC LIMIT 1""",
            (job_id,),
        ).fetchone()
        if not payment:
            return False, "Bu ish uchun to‘lov topilmadi", None
        payment_id,payment_uuid,payer_id,payee_id,amount,status = payment
        if status == "refunded":
            return True, "already_refunded", {"amount": float(amount)}
        if status != "held":
            return False, "Faqat waiting holatidagi to‘lovni refund qilish mumkin", None

        amount = float(amount)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE platform_wallet SET escrow_balance=ROUND(escrow_balance-?,2) WHERE id=1 AND escrow_balance>=?",
                (amount, amount),
            )
            if cur.rowcount != 1:
                raise ValueError("escrow_insufficient")
            cur.execute("UPDATE users SET balance=ROUND(COALESCE(balance,0)+?,2) WHERE id=?", (amount, payer_id))
            payer_after = cur.execute("SELECT COALESCE(balance,0) FROM users WHERE id=?", (payer_id,)).fetchone()[0]
            cur.execute(
                "UPDATE payments SET status='refunded',refunded_at=?,provider_payload=? WHERE id=? AND status='held'",
                (now, json.dumps({"refund": True, "amount": amount}, ensure_ascii=False), payment_id),
            )
            if cur.rowcount != 1:
                raise ValueError("payment_state_changed")
            _wallet_tx(cur, payer_id, "payment_refund", amount, payer_after, job_id, f"«{job[4]}» bo‘yicha refund", now)
            conn.commit()
        except Exception as e:
            conn.rollback()
            if str(e) == "escrow_insufficient":
                return False, "Escrow balansida yetarli mablag‘ yo‘q", None
            if str(e) == "payment_state_changed":
                return False, "To‘lov holati o‘zgardi", None
            raise
        finally:
            conn.close()

        create_notification(payer_id, "payment_refunded", "To‘lov qaytarildi",
            f"«{job[4]}» bo‘yicha {amount:,.0f} UZS to‘liq refund qilindi.", "/payments")
        if payee_id:
            create_notification(payee_id, "payment_refunded", "To‘lov refund qilindi",
                f"«{job[4]}» bo‘yicha admin qarori sabab waiting to‘lovi qaytarildi.", "/payments")
        return True, "refunded", {"amount": amount}

    app.config["FINJOB_RELEASE_PAYMENT"] = release_payment
    app.config["FINJOB_REFUND_PAYMENT"] = refund_payment

    @app.route("/payments/dummy/<int:job_id>", methods=["POST"])
    @auth
    def dummy_payment(job_id):
        if enforce_block:
            block_response=enforce_block("full")
            if block_response: return block_response

        job = db.q("SELECT user_id,worker_id,status,COALESCE(agreed_price,price),currency,title FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return jsonify({"msg": "Ish topilmadi"}), 404
        owner_id, worker_id, job_status, price, currency, title = job
        if owner_id != request.uid:
            return jsonify({"msg": "To‘lovni faqat ish egasi amalga oshirishi mumkin"}), 403
        if job_status != "payment_pending" or not worker_id:
            return jsonify({"msg": "Bu ish hozir to‘lov uchun tayyor emas"}), 400
        if float(price) <= 0:
            return jsonify({"msg": "Ish narxi noto‘g‘ri"}), 400

        existing = db.q("SELECT payment_uuid,status FROM payments WHERE job_id=? AND provider='dummy'", (job_id,)).fetchone()
        if existing and existing[1] == "held":
            return jsonify({"msg": "already_paid", "status": "held", "payment_uuid": existing[0]})
        if existing and existing[1] in ("released", "refunded"):
            return jsonify({"msg": "already_processed", "status": existing[1]})

        payer_balance = db.q("SELECT COALESCE(balance,0) FROM users WHERE id=?", (owner_id,)).fetchone()
        amount = float(price)
        if not payer_balance or float(payer_balance[0]) < amount:
            return jsonify({"msg": "Hisobingizda mablag‘ yetarli emas", "required": amount, "balance": float(payer_balance[0]) if payer_balance else 0}), 400

        payment_uuid = existing[0] if existing else str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            payload = json.dumps({"test": True, "escrow": True}, ensure_ascii=False)
            if existing:
                cur.execute(
                    """UPDATE payments SET payer_id=?,payee_id=?,amount=?,currency='UZS',
                       status='held',paid_at=?,provider_payload=?
                       WHERE payment_uuid=? AND provider='dummy'""",
                    (owner_id, worker_id, amount, now, payload, payment_uuid),
                )
            else:
                cur.execute(
                    """INSERT INTO payments(
                        payment_uuid,job_id,payer_id,payee_id,amount,currency,provider,status,
                        provider_payload,created_at,paid_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (payment_uuid,job_id,owner_id,worker_id,amount,"UZS","dummy","held",payload,now,now),
                )
            cur.execute(
                "UPDATE users SET balance=ROUND(COALESCE(balance,0)-?,2) WHERE id=? AND COALESCE(balance,0)>=?",
                (amount, owner_id, amount),
            )
            if cur.rowcount != 1:
                raise ValueError("insufficient_balance")
            cur.execute(
                """CREATE TABLE IF NOT EXISTS platform_wallet(
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    balance REAL NOT NULL DEFAULT 0,
                    escrow_balance REAL NOT NULL DEFAULT 0
                )"""
            )
            platform_columns = [row[1] for row in cur.execute("PRAGMA table_info(platform_wallet)").fetchall()]
            if "escrow_balance" not in platform_columns:
                cur.execute("ALTER TABLE platform_wallet ADD COLUMN escrow_balance REAL NOT NULL DEFAULT 0")
            cur.execute("INSERT OR IGNORE INTO platform_wallet(id,balance,escrow_balance) VALUES(1,0,0)")
            cur.execute("UPDATE platform_wallet SET escrow_balance=ROUND(escrow_balance+?,2) WHERE id=1", (amount,))
            cur.execute(
                """CREATE TABLE IF NOT EXISTS wallet_transactions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    balance_after REAL NOT NULL,
                    job_id INTEGER,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            payer_after = cur.execute("SELECT balance FROM users WHERE id=?", (owner_id,)).fetchone()[0]
            _wallet_tx(cur, owner_id, "payment_hold", -amount, payer_after, job_id, f"«{title}» uchun waiting to‘lovi", now)
            cur.execute("UPDATE jobs SET status='accepted' WHERE id=? AND status='payment_pending'", (job_id,))
            if cur.rowcount != 1:
                raise ValueError("job_state_changed")
            conn.commit()
        except Exception as e:
            conn.rollback()
            if str(e) == "insufficient_balance":
                return jsonify({"msg": "Hisobingizda mablag‘ yetarli emas"}), 400
            if str(e) == "job_state_changed":
                return jsonify({"msg": "Ish holati o‘zgardi. Qayta urinib ko‘ring"}), 409
            raise
        finally:
            conn.close()

        create_notification(owner_id, "payment_success", "To‘lov waiting holatiga o‘tdi",
            f"«{title}» uchun {amount:,.0f} UZS yechildi va ish yakunlanguncha FinJob escrowida saqlanadi.", "/payments")
        create_notification(worker_id, "payment_held", "To‘lov waiting holatida",
            f"«{title}» uchun {amount:,.0f} UZS to‘lov qilingan. Ish yakunlangach va tasdiqlangach pul balansingizga o‘tadi.", "/jobs")
        return jsonify({"msg": "ok", "status": "held", "payment_uuid": payment_uuid, "amount": amount, "currency": "UZS", "provider": "dummy"})

    @app.route("/payments/release/<int:job_id>", methods=["POST"])
    @auth
    def release_payment_route(job_id):
        if enforce_block:
            block_response=enforce_block("full")
            if block_response: return block_response

        job = db.q("SELECT user_id,worker_id,status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job or job[1] != request.uid:
            return jsonify({"msg": "Faqat shu ishning hozirgi ishchisi to‘lovni yakunlay oladi"}), 403
        if job[2] != "finished":
            return jsonify({"msg": "Ish hali ikki tomon tomonidan yakunlanmagan"}), 400
        ok, message, data = release_payment(job_id)
        if not ok:
            return jsonify({"msg": message}), 400
        return jsonify({"msg": "ok", "status": "released", **(data or {})})

    @app.route("/payments/refund/<int:job_id>", methods=["POST"])
    @admin_required
    def refund_payment_route(job_id):
        ok, message, data = refund_payment(job_id)
        if not ok:
            return jsonify({"msg": message}), 400
        return jsonify({"msg": "ok", "status": "refunded", **(data or {})})

    @app.route("/wallet")
    @auth
    def get_wallet():
        user = db.q("SELECT COALESCE(balance,0) FROM users WHERE id=?", (request.uid,)).fetchone()
        transactions = db.q(
            """SELECT type,amount,balance_after,job_id,description,created_at
               FROM wallet_transactions WHERE user_id=? ORDER BY id DESC LIMIT 100""",
            (request.uid,),
        ).fetchall() if db.q(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='wallet_transactions'"
        ).fetchone() else []
        return jsonify({
            "balance": float(user[0]) if user else 0,
            "transactions": [
                {"type": x[0], "amount": x[1], "balance_after": x[2], "job_id": x[3],
                 "description": x[4], "created_at": x[5]}
                for x in transactions
            ],
        })


    @app.route("/wallet/withdraw", methods=["POST"])
    @auth
    def withdraw_wallet():
        if enforce_block:
            block_response=enforce_block("withdrawal")
            if block_response: return block_response

        data = request.json or {}
        try:
            amount = float(data.get("amount", 0))
        except (TypeError, ValueError):
            return jsonify({"msg": "Summa noto‘g‘ri"}), 400

        if not amount or amount <= 0:
            return jsonify({"msg": "Yechib olish summasi 0 dan katta bo‘lishi kerak"}), 400
        if amount > 1000000000:
            return jsonify({"msg": "Bir martalik yechib olish 1 000 000 000 UZS dan oshmasligi kerak"}), 400

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        withdrawal_fee = 0.0
        withdrawal_net = round(amount - withdrawal_fee, 2)

        conn = db.get_connection()
        try:
            cur = conn.cursor()
            current = cur.execute("SELECT COALESCE(balance,0) FROM users WHERE id=?", (request.uid,)).fetchone()
            if not current:
                conn.rollback()
                return jsonify({"msg": "Foydalanuvchi topilmadi"}), 404

            balance = float(current[0] or 0)
            if withdrawal_net > balance:
                conn.rollback()
                return jsonify({"msg": "Balansda yetarli mablag‘ yo‘q", "balance": balance}), 400

            cur.execute(
                "UPDATE users SET balance=ROUND(COALESCE(balance,0)-?,2) WHERE id=? AND COALESCE(balance,0)>=?",
                (withdrawal_net, request.uid, withdrawal_net),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return jsonify({"msg": "Balans o‘zgardi. Qayta urinib ko‘ring"}), 409

            balance_after = cur.execute(
                "SELECT COALESCE(balance,0) FROM users WHERE id=?", (request.uid,)
            ).fetchone()[0]

            _wallet_tx(
                cur,
                request.uid,
                "withdrawal",
                -withdrawal_net,
                balance_after,
                None,
                "Test wallet orqali balansdan mablag‘ yechildi (qo‘shimcha withdrawal komissiyasi 0%)",
                now,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        create_notification(
            request.uid,
            "wallet_withdrawal",
            "Mablag‘ yechildi",
            f"{amount:,.0f} UZS balansingizdan yechildi.",
            "/profile",
        )
        return jsonify({
            "msg": "ok",
            "amount": withdrawal_net,
            "requested_amount": amount,
            "withdrawal_fee": withdrawal_fee,
            "balance": float(balance_after),
        })


    @app.route("/admin/wallet/<int:user_id>", methods=["POST"])
    @admin_required
    def admin_add_wallet(user_id):
        data = request.json or {}
        try:
            amount = float(data.get("amount", 0))
        except (TypeError, ValueError):
            return jsonify({"msg": "Summa noto‘g‘ri"}), 400
        if amount <= 0 or amount > 1000000000:
            return jsonify({"msg": "Summa 0 dan katta va 1 000 000 000 UZS dan oshmasligi kerak"}), 400

        target = db.q("SELECT id,username FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            return jsonify({"msg": "Foydalanuvchi topilmadi"}), 404

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET balance=ROUND(COALESCE(balance,0)+?,2) WHERE id=?",
                (amount,user_id),
            )
            balance = cur.execute("SELECT COALESCE(balance,0) FROM users WHERE id=?", (user_id,)).fetchone()[0]
            cur.execute(
                """CREATE TABLE IF NOT EXISTS wallet_transactions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    balance_after REAL NOT NULL,
                    job_id INTEGER,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            cur.execute(
                """INSERT INTO wallet_transactions
                   (user_id,type,amount,balance_after,job_id,description,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (user_id,"admin_topup",amount,balance,None,"Admin tomonidan test balansi qo‘shildi",now),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        if admin_audit:
            admin_audit("wallet_topup","user",user_id,f"amount={amount:g}")
        create_notification(
            user_id,"wallet_topup","Test balansi to‘ldirildi",
            f"Admin hisobingizga {amount:,.0f} UZS test mablag‘i qo‘shdi.",
            "/payments"
        )
        return jsonify({"msg": "Test balansi qo‘shildi", "balance": float(balance)})


    @app.route("/admin/wallet/summary")
    @admin_required
    def admin_wallet_summary():
        rows = db.q(
            """SELECT id,username,first_name,last_name,COALESCE(balance,0)
               FROM users ORDER BY balance DESC, id DESC"""
        ).fetchall()
        platform = db.q(
            "SELECT balance,COALESCE(escrow_balance,0) FROM platform_wallet WHERE id=1"
        ).fetchone() if db.q(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='platform_wallet'"
        ).fetchone() else None
        return jsonify({
            "platform_balance": float(platform[0]) if platform else 0,
            "escrow_balance": float(platform[1]) if platform else 0,
            "users": [
                {"id":x[0],"username":x[1],"first_name":x[2],"last_name":x[3],"balance":float(x[4] or 0)}
                for x in rows
            ],
        })

    @app.route("/payments/click", methods=["POST","GET"])
    def click_callback():
        data = request.form.to_dict() if request.method == "POST" else request.args.to_dict()
        required = ["click_trans_id","service_id","click_paydoc_id","merchant_trans_id","amount","action","sign_time","sign_string"]
        if any(key not in data for key in required):
            return click_error(-8, "Required parameters are missing")
        if not CLICK_SERVICE_ID or not CLICK_SECRET_KEY:
            return click_error(-8, "Click integration is not configured")

        try:
            click_trans_id = str(data["click_trans_id"])
            service_id = str(data["service_id"])
            merchant_trans_id = str(data["merchant_trans_id"])
            amount = float(data["amount"])
            action = int(data["action"])
            sign_time = str(data["sign_time"])
        except (TypeError,ValueError):
            return click_error(-8, "Invalid parameters")

        if not math.isfinite(amount) or amount <= 0:
            return click_error(-2, "Incorrect amount")

        if service_id != CLICK_SERVICE_ID:
            return click_error(-3, "Service not found")

        expected = click_signature(
            click_trans_id,service_id,CLICK_SECRET_KEY,
            merchant_trans_id,data["amount"],action,sign_time
        )
        if not secrets.compare_digest(expected,str(data["sign_string"]).lower()):
            return click_error(-1, "SIGN CHECK FAILED")

        payment = db.q(
            """SELECT id,payment_uuid,job_id,payer_id,payee_id,amount,currency,status
               FROM payments WHERE payment_uuid=? AND provider='click'""",
            (merchant_trans_id,),
        ).fetchone()
        if not payment:
            return click_error(-5, "Transaction does not exist")

        payment_id,payment_uuid,job_id,payer_id,payee_id,expected_amount,currency,payment_status = payment
        if str(currency).upper() != "UZS" or not math.isfinite(float(expected_amount)) or abs(amount-float(expected_amount)) > 0.001:
            return click_error(-2, "Incorrect amount")

        current_job = db.q(
            "SELECT user_id,worker_id,status FROM jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if not current_job:
            return click_error(-5, "Transaction does not exist")
        if current_job[0] != payer_id or current_job[1] != payee_id:
            return click_error(-2, "Transaction is no longer assigned to this worker")
        if action == 0 and current_job[2] != "payment_pending":
            return click_error(-2, "Transaction is not ready for payment")

        if action == 0:
            db.q(
                """UPDATE payments
                   SET provider_transaction_id=?,provider_prepare_id=?,provider_payload=?
                   WHERE id=?""",
                (click_trans_id,str(payment_id),json.dumps(data,ensure_ascii=False),payment_id),
            ).close()
            return jsonify({
                "click_trans_id": click_trans_id,
                "merchant_trans_id": payment_uuid,
                "merchant_prepare_id": str(payment_id),
                "error": 0,
                "error_note": "Success",
            })

        if action != 1:
            return click_error(-3, "Action not found")

        duplicate_transaction = db.q(
            "SELECT id FROM payments WHERE provider='click' AND provider_transaction_id=? AND id!=?",
            (click_trans_id, payment_id),
        ).fetchone()
        if duplicate_transaction:
            return click_error(-4, "Transaction already processed")

        if payment_status in ("held", "released"):
            return jsonify({
                "click_trans_id": click_trans_id,
                "merchant_trans_id": payment_uuid,
                "merchant_confirm_id": str(payment_id),
                "error": 0,
                "error_note": "Success",
            })

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE payments SET provider_transaction_id=?,provider_payload=?,
                   status='held',paid_at=? WHERE id=? AND status='pending'""",
                (click_trans_id,json.dumps(data,ensure_ascii=False),now,payment_id),
            )
            changed = cursor.rowcount
            if changed:
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS platform_wallet(
                        id INTEGER PRIMARY KEY CHECK(id=1),
                        balance REAL NOT NULL DEFAULT 0,
                        escrow_balance REAL NOT NULL DEFAULT 0
                    )"""
                )
                platform_columns = [row[1] for row in cursor.execute("PRAGMA table_info(platform_wallet)").fetchall()]
                if "escrow_balance" not in platform_columns:
                    cursor.execute("ALTER TABLE platform_wallet ADD COLUMN escrow_balance REAL NOT NULL DEFAULT 0")
                cursor.execute("INSERT OR IGNORE INTO platform_wallet(id,balance,escrow_balance) VALUES(1,0,0)")
                cursor.execute(
                    "UPDATE platform_wallet SET escrow_balance=ROUND(escrow_balance+?,2) WHERE id=1",
                    (float(expected_amount),),
                )
                cursor.execute(
                    "UPDATE jobs SET status='accepted' WHERE id=? AND status='payment_pending'",
                    (job_id,),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            return click_error(-9, "Temporary database error")
        finally:
            conn.close()

        if changed:
            create_notification(
                payer_id,"payment_success","To‘lov muvaffaqiyatli amalga oshdi",
                f"«{payment_uuid}» to‘lovingiz qabul qilindi va ish yakunlanguncha ushlab turiladi.","/payments"
            )
            create_notification(
                payee_id,"payment_received","To‘lov qabul qilindi",
                "Ish bo‘yicha to‘lov qabul qilindi. Ish yakunlangach va tasdiqlangach pul balansingizga o‘tadi.","/jobs"
            )

        return jsonify({
            "click_trans_id": click_trans_id,
            "merchant_trans_id": payment_uuid,
            "merchant_confirm_id": str(payment_id),
            "error": 0,
            "error_note": "Success",
        })
