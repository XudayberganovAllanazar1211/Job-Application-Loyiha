import datetime
import hashlib
import json
import os
import secrets
import uuid
from urllib.parse import urlencode
from flask import jsonify, request


CLICK_SERVICE_ID = os.environ.get("CLICK_SERVICE_ID", "").strip()
CLICK_MERCHANT_ID = os.environ.get("CLICK_MERCHANT_ID", "").strip()
CLICK_SECRET_KEY = os.environ.get("CLICK_SECRET_KEY", "").strip()
CLICK_RETURN_URL = os.environ.get("CLICK_RETURN_URL", "http://localhost:5173/jobs").strip()
CLICK_CHECKOUT_URL = "https://my.click.uz/services/pay"


def register_payment_routes(app, db, auth, create_notification):
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

    @app.route("/payments/config")
    @auth
    def payment_config():
        return jsonify({
            "click_enabled": bool(CLICK_SERVICE_ID and CLICK_MERCHANT_ID and CLICK_SECRET_KEY),
            "providers": ["click"] if CLICK_SERVICE_ID and CLICK_MERCHANT_ID and CLICK_SECRET_KEY else [],
        })

    @app.route("/payments/create/<int:job_id>", methods=["POST"])
    @auth
    def create_payment(job_id):
        job = db.q(
            "SELECT user_id,worker_id,status,price,currency,title FROM jobs WHERE id=?",
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
            return jsonify({"msg": "Click to‘lov tizimi merchant ma’lumotlari bilan sozlanmagan"}), 503

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
        if request.uid not in (payment[2],payment[3]):
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
               WHERE p.payer_id=? OR p.payee_id=?
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
        if str(currency).upper() != "UZS" or abs(amount-float(expected_amount)) > 0.01:
            return click_error(-2, "Incorrect amount")

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

        if payment_status == "paid":
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
                   status='paid',paid_at=? WHERE id=? AND status!='paid'""",
                (click_trans_id,json.dumps(data,ensure_ascii=False),now,payment_id),
            )
            changed = cursor.rowcount
            if changed:
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
                f"«{payment_uuid}» to‘lovingiz muvaffaqiyatli qabul qilindi.","/payments"
            )
            create_notification(
                payee_id,"payment_received","To‘lov qabul qilindi",
                "Ish bo‘yicha to‘lov muvaffaqiyatli qabul qilindi. Endi ishni bajarishingiz mumkin.","/jobs"
            )

        return jsonify({
            "click_trans_id": click_trans_id,
            "merchant_trans_id": payment_uuid,
            "merchant_confirm_id": str(payment_id),
            "error": 0,
            "error_note": "Success",
        })
