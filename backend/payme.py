"""Payme wallet top-ups for FinJob.

Protocol: Payme "Payment API" documented at https://docs.payme.uz/ :
  * order creation   POST {base}/api/checkout/url   -> hosted checkout_url
  * order status     POST {base}/api/status/order_id
  * server callback  POST to our `server_callback_url` (must answer HTTP 200)
  * signature        sha1(secret|v1|v2|...) over all non-empty request/response
                     parameters sorted by parameter name (docs: "Building signature")

This module only credits a FinJob wallet from a *verified* Payme order status
(`order_status == "approved"`), delivered either by the signed server callback or
by a signed answer to our own status request. Browser redirects never credit.

Deposits live in their own `wallet_deposits` table; they are unrelated to the
job `payments` table (which has job_id NOT NULL UNIQUE).
"""
import datetime
import hashlib
import json
import os
import re
import secrets
import sqlite3
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlencode, urlsplit

from flask import jsonify, redirect, request

PAYME_TEST_MERCHANT_ID = "4056281"  # public test merchant from docs.payme.uz/api/testing
DEPOSIT_STATUSES = (
    "pending", "processing", "credited", "declined", "expired", "cancelled", "failed", "reversed",
)
OPEN_STATUSES = ("pending", "processing")
_UUID_RE = re.compile(r"^[0-9a-f]{32}$")
_DIGITS_RE = re.compile(r"^[0-9]{1,15}$")


# Amount units. Two separate worlds, never mixed:
#   * FinJob wallet / UI / users.balance / wallet_deposits.amount_uzs : whole UZS (sum)
#   * Everything exchanged with Payme (request amount, callback amount/actual_amount,
#     wallet_deposits.amount_minor) : integer tiyin, no decimal separator (100020 = 1000 UZS 20 tiyin).
# The ONLY conversion point is uzs_to_tiyin(); the wallet is credited from amount_uzs, never from Payme values.
TIYIN_PER_UZS = 100
PAYME_MAX_MINOR_AMOUNT = 999_999_999_999  # Payme `amount` is integer(12)


def uzs_to_tiyin(amount_uzs):
    return int(amount_uzs) * TIYIN_PER_UZS


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt):
    return dt.isoformat()


def load_config():
    """Read configuration from the environment on every call (testable, no import-time state)."""
    env = os.environ
    production = env.get("FINJOB_ENV", "development").strip().lower() in {"production", "prod"}
    test_mode_raw = env.get("PAYME_TEST_MODE", "").strip()
    cfg = {
        "production": production,
        "switch": _truthy(env.get("PAYME_ENABLED")),
        "test_mode": _truthy(test_mode_raw),
        "test_mode_set": test_mode_raw != "",
        "merchant_id": env.get("PAYME_MERCHANT_ID", "").strip(),
        "merchant_key": env.get("PAYME_MERCHANT_KEY", "").strip(),
        "base_url": env.get("PAYME_CHECKOUT_BASE_URL", "https://pay.payme.uz").strip().rstrip("/"),
        "callback_url": env.get("PAYME_CALLBACK_URL", "").strip(),
        "response_url": env.get("PAYME_RESPONSE_URL", "").strip(),
        "frontend_return_url": env.get("PAYME_FRONTEND_RETURN_URL", "").strip(),
        "ip_allowlist": [x.strip() for x in env.get("PAYME_CALLBACK_IP_ALLOWLIST", "").split(",") if x.strip()],
    }
    for name, default in (
        ("lifetime", 3600), ("min_uzs", 1000), ("max_uzs", 50_000_000), ("max_open", 5),
    ):
        env_name = {
            "lifetime": "PAYME_ORDER_LIFETIME_SECONDS", "min_uzs": "PAYME_MIN_AMOUNT_UZS",
            "max_uzs": "PAYME_MAX_AMOUNT_UZS", "max_open": "PAYME_MAX_OPEN_DEPOSITS",
        }[name]
        try:
            cfg[name] = int(env.get(env_name, default))
        except (TypeError, ValueError):
            cfg[name] = default
    cfg["lifetime"] = max(300, min(86400, cfg["lifetime"]))
    cfg["problems"] = config_problems(cfg)
    cfg["enabled"] = not cfg["problems"]
    return cfg


def config_problems(cfg):
    """Explicit opt-in; anything ambiguous disables the integration (fail safe)."""
    problems = []
    if not cfg["switch"]:
        problems.append("PAYME_ENABLED is not 1")
    if not cfg["test_mode_set"]:
        problems.append("PAYME_TEST_MODE must be set explicitly to 1 or 0")
    if not cfg["merchant_id"].isdigit():
        problems.append("PAYME_MERCHANT_ID missing/invalid")
    if not cfg["merchant_key"]:
        problems.append("PAYME_MERCHANT_KEY missing")
    if not cfg["callback_url"]:
        problems.append("PAYME_CALLBACK_URL missing")
    if uzs_to_tiyin(cfg["max_uzs"]) > PAYME_MAX_MINOR_AMOUNT:
        problems.append("PAYME_MAX_AMOUNT_UZS exceeds Payme's integer(12) amount field")
    if not cfg["response_url"] or not cfg["frontend_return_url"]:
        problems.append("PAYME_RESPONSE_URL and PAYME_FRONTEND_RETURN_URL are required")
    if cfg["production"] and cfg["test_mode"]:
        problems.append("test mode is refused when FINJOB_ENV=production")
    if not cfg["test_mode"] and cfg["merchant_id"] == PAYME_TEST_MERCHANT_ID:
        problems.append("live mode cannot use the public test merchant")
    if not cfg["test_mode"] and cfg["callback_url"] and not cfg["callback_url"].lower().startswith("https://"):
        problems.append("live PAYME_CALLBACK_URL must be https")
    if cfg["base_url"] and not cfg["base_url"].lower().startswith("https://"):
        problems.append("PAYME_CHECKOUT_BASE_URL must be https")
    if cfg["min_uzs"] <= 0 or cfg["max_uzs"] < cfg["min_uzs"]:
        problems.append("invalid min/max amount limits")
    return problems


# ---------------------------------------------------------------- signature
def payme_signature_string(secret, params):
    """docs.payme.uz/api/building-signature: secret + all non-empty params sorted by name, '|' separated."""
    parts = [secret]
    for key in sorted(params.keys()):
        if key in ("signature", "response_signature_string"):
            continue
        value = params[key]
        if value is None or value == "":
            continue
        parts.append(str(value))
    return "|".join(parts)


def payme_signature(secret, params):
    return hashlib.sha1(payme_signature_string(secret, params).encode("utf-8")).hexdigest()


def verify_signature(secret, payload):
    given = str(payload.get("signature", "")).strip().lower()
    if not given or not secret:
        return False
    # Compare as bytes: secrets.compare_digest raises TypeError on non-ASCII str (would be a 500 on hostile input).
    return secrets.compare_digest(payme_signature(secret, payload).encode("utf-8"), given.encode("utf-8"))


def _http_post_json(url, body, timeout=15):
    """Server-to-server call to Payme. Isolated so tests can mock it (no real requests in tests)."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL comes from config, https enforced)
        return json.loads(resp.read().decode("utf-8"))


def _parse_amount(value, max_digits=15):
    """Strict non-negative integer from int or digit-string; None if anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and _DIGITS_RE.match(value.strip()):
        return int(value.strip())
    return None


def register_payme_routes(app, db, auth, create_notification, enforce_block=None):
    log = app.logger

    # ------------------------------------------------------------ schema
    def ensure_schema():
        conn = db.get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wallet_deposits(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deposit_uuid TEXT NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    amount_uzs INTEGER NOT NULL CHECK(amount_uzs > 0),
                    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                    currency TEXT NOT NULL DEFAULT 'UZS' CHECK(currency = 'UZS'),
                    provider TEXT NOT NULL DEFAULT 'payme' CHECK(provider = 'payme'),
                    provider_payment_id TEXT,
                    provider_status TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','processing','credited','declined','expired','cancelled','failed','reversed')),
                    is_test INTEGER NOT NULL DEFAULT 0,
                    checkout_url TEXT DEFAULT '',
                    wallet_transaction_id INTEGER,
                    review_required INTEGER NOT NULL DEFAULT 0,
                    review_note TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    provider_created_at TEXT,
                    paid_at TEXT,
                    credited_at TEXT,
                    cancelled_at TEXT,
                    cancel_reason TEXT,
                    reversed_at TEXT,
                    last_event_at TEXT
                )
            """)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_wallet_deposits_provider_payment "
                "ON wallet_deposits(provider, provider_payment_id) WHERE provider_payment_id IS NOT NULL AND provider_payment_id != ''"
            )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wallet_deposit_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deposit_uuid TEXT,
                    source TEXT NOT NULL,
                    order_status TEXT,
                    outcome TEXT NOT NULL,
                    http_status INTEGER NOT NULL,
                    flagged INTEGER NOT NULL DEFAULT 0,
                    provider_payment_id TEXT,
                    amount TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wallet_deposit_events_dep ON wallet_deposit_events(deposit_uuid, id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wallet_deposits_user ON wallet_deposits(user_id, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wallet_deposits_status ON wallet_deposits(status, created_at)")
            conn.commit()
        finally:
            conn.close()

    _ready = set()

    def schema():
        """Create the table on first use of each database file (also covers test/alternate DBs)."""
        if db.db_name not in _ready:
            ensure_schema()
            _ready.add(db.db_name)

    schema()

    COLS = (
        "id,deposit_uuid,user_id,amount_uzs,amount_minor,currency,provider_payment_id,status,is_test,"
        "checkout_url,created_at,expires_at,paid_at,credited_at,cancelled_at,cancel_reason,review_required,reversed_at"
    )

    def public_view(row):
        return {
            "deposit_id": row[1], "amount": row[3], "currency": row[5], "provider": "payme",
            "status": row[7], "test": bool(row[8]), "created_at": row[10], "expires_at": row[11],
            "paid_at": row[12], "credited_at": row[13], "cancelled_at": row[14],
            "cancel_reason": row[15] or "",
        }

    def get_deposit(deposit_uuid):
        return db.q(f"SELECT {COLS} FROM wallet_deposits WHERE deposit_uuid=?", (deposit_uuid,)).fetchone()

    # ------------------------------------------------ core state machine
    def _apply(payload, source, cfg):
        """Validate a *signature-verified* Payme order object and apply it. Returns (http_status, body).

        Safe to call repeatedly with the same payload (idempotent).
        """
        order_id = str(payload.get("order_id", "")).strip()
        if not _UUID_RE.match(order_id):
            return 404, {"status": "unknown_order"}
        row = get_deposit(order_id)
        if not row:
            return 404, {"status": "unknown_order"}
        dep_id, user_id, amount_uzs, amount_minor, status = row[0], row[2], row[3], row[4], row[7]

        if str(payload.get("merchant_id", "")).strip() != cfg["merchant_id"]:
            return 400, {"status": "merchant_mismatch"}
        if str(payload.get("currency", "")).strip().upper() != "UZS":
            return 400, {"status": "currency_mismatch"}
        if bool(row[8]) != bool(cfg["test_mode"]):
            return 400, {"status": "mode_mismatch"}
        amount = _parse_amount(payload.get("amount"))
        if amount is None or amount != amount_minor:
            return 400, {"status": "amount_mismatch"}

        if str(payload.get("response_status", "")).strip().lower() != "success":
            return 400, {"status": "response_status_not_success"}
        new_status = str(payload.get("order_status", "")).strip().lower()
        payment_id = str(payload.get("payment_id", "") or "").strip()
        stored_payment_id = row[6] or ""
        if payment_id and not _DIGITS_RE.match(payment_id):
            return 400, {"status": "bad_payment_id"}
        if payment_id and stored_payment_id and payment_id != stored_payment_id:
            return 400, {"status": "payment_id_mismatch"}
        now = _iso(_now())

        if new_status == "approved":
            actual = payload.get("actual_amount")
            if actual not in (None, "") and _parse_amount(actual) != amount_minor:
                return 400, {"status": "actual_amount_mismatch"}
            actual_cur = str(payload.get("actual_currency", "") or "").upper()
            if actual_cur not in ("", "UZS"):
                return 400, {"status": "actual_currency_mismatch"}
            reversal = payload.get("reversal_amount")
            if reversal not in (None, "") and _parse_amount(reversal) != 0:
                # approved but (partially) reversed: do not credit, a human must decide.
                if status in OPEN_STATUSES:
                    flag_review(dep_id, "approved with non-zero reversal_amount")
                    log.error("payme: approved with reversal_amount for deposit %s (flagged, not credited)", order_id)
                    return 409, {"status": "reversal_present"}
                if status == "credited":
                    flag_review(dep_id, "partial reversal reported after credit; wallet NOT debited automatically")
                    log.error("payme: reversal_amount reported for credited deposit %s (flagged)", order_id)
                    return 200, {"status": "reversal_flagged"}
            if status == "credited":
                return 200, {"status": "already_credited"}
            if status not in OPEN_STATUSES:
                flag_review(dep_id, f"approved received while deposit is {status}")
                log.error("payme: approved for deposit %s in state %s (flagged)", order_id, status)
                return 409, {"status": "invalid_transition"}
            return credit_deposit(dep_id, user_id, amount_uzs, order_id, payment_id, payload, now)

        if new_status in ("declined", "expired"):
            if status == new_status:
                return 200, {"status": "already_" + new_status}
            if status not in OPEN_STATUSES:
                return 409, {"status": "invalid_transition"}
            return mark_terminal(dep_id, new_status, payment_id, payload, now)

        if new_status in ("created", "processing"):
            if status in OPEN_STATUSES:
                db.q(
                    "UPDATE wallet_deposits SET status=CASE WHEN ?='processing' THEN 'processing' ELSE status END,"
                    "provider_status=?,provider_payment_id=COALESCE(NULLIF(provider_payment_id,''),NULLIF(?,'')),last_event_at=? "
                    "WHERE id=? AND status IN ('pending','processing')",
                    (new_status, new_status, payment_id, now, dep_id),
                ).close()
                return 200, {"status": "noted"}
            return 200, {"status": "stale_ignored"}  # late created/processing after a final state: harmless

        if new_status == "reversed":
            if status == "reversed":
                return 200, {"status": "already_reversed"}
            if status != "credited":
                return 409, {"status": "invalid_transition"}
            # Money was already credited and may be spent: never auto-debit, flag for manual review.
            db.q(
                "UPDATE wallet_deposits SET status='reversed',reversed_at=?,review_required=1,"
                "review_note='Payme reversed an already credited deposit; wallet NOT debited automatically',"
                "provider_status='reversed',last_event_at=? WHERE id=? AND status='credited'",
                (now, now, dep_id),
            ).close()
            log.error("payme: deposit %s reversed after credit; manual review required", order_id)
            return 200, {"status": "reversed_flagged"}

        return 400, {"status": "unknown_order_status"}

    # Outcomes where a retry could still succeed once an operator fixes configuration, or where our own
    # database failed: these keep a non-200 answer so Payme retries (2s,1m,5m,10m,1h,24h per docs).
    RETRYABLE = {"temporary_error", "merchant_mismatch", "mode_mismatch"}

    def record_event(order_id, source, payload, code, outcome, flagged):
        try:
            db.q(
                "INSERT INTO wallet_deposit_events(deposit_uuid,source,order_status,outcome,http_status,flagged,"
                "provider_payment_id,amount,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (order_id if _UUID_RE.match(order_id) else None, source,
                 str(payload.get("order_status", ""))[:30], outcome, code, 1 if flagged else 0,
                 str(payload.get("payment_id", "") or "")[:30], str(payload.get("amount", ""))[:20], _iso(_now())),
            ).close()
        except Exception:  # noqa: BLE001 - the audit write must never break payment processing
            log.exception("payme: could not write audit event for %s", order_id[:40])

    def apply_order_update(payload, source, cfg):
        """Signed Payme order data in -> (http_status, body) out, with an audit trail.

        Callback HTTP contract (docs.payme.uz/api/callbacks): 200 = processed, anything else = Payme retries and
        does not follow redirects. Therefore every *valid, signed* callback that we have fully handled (credited,
        duplicate, or rejected-and-flagged for manual review) answers 200; only temporary failures and
        operator-fixable config problems answer non-200 so retries continue.
        """
        order_id = str(payload.get("order_id", "")).strip()
        code, body = _apply(payload, source, cfg)
        outcome = body.get("status", "")
        flagged = False
        if code != 200 and outcome not in RETRYABLE:
            flagged = True
            row = get_deposit(order_id) if _UUID_RE.match(order_id) else None
            if row:
                flag_review(row[0], f"callback not applied: {outcome}")
            log.error("payme: signed callback not applied (%s) for order %s: flagged, answering 200 to stop retries",
                      outcome, order_id[:40])
            record_event(order_id, source, payload, code, outcome, True)
            return 200, {"status": outcome, "flagged": True}
        record_event(order_id, source, payload, code, outcome, flagged)
        return code, body

    def flag_review(dep_id, note):
        db.q(
            "UPDATE wallet_deposits SET review_required=1,review_note=?,last_event_at=? WHERE id=?",
            (note[:300], _iso(_now()), dep_id),
        ).close()

    def mark_terminal(dep_id, new_status, payment_id, payload, now):
        reason = str(payload.get("response_description", "") or "")[:200]
        try:
            db.q(
                "UPDATE wallet_deposits SET status=?,provider_status=?,cancelled_at=?,cancel_reason=?,"
                "provider_payment_id=COALESCE(NULLIF(provider_payment_id,''),NULLIF(?,'')),last_event_at=? "
                "WHERE id=? AND status IN ('pending','processing')",
                (new_status, new_status, now, reason or new_status, payment_id, now, dep_id),
            ).close()
        except sqlite3.IntegrityError:
            return 409, {"status": "payment_id_conflict"}
        return 200, {"status": new_status}

    def credit_deposit(dep_id, user_id, amount_uzs, order_id, payment_id, payload, now):
        """Atomic, once-only wallet credit. All writes commit together or not at all."""
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")  # serialise concurrent callbacks
            cur.execute(
                """UPDATE wallet_deposits
                   SET status='credited',credited_at=?,paid_at=?,provider_status='approved',last_event_at=?,
                       provider_payment_id=COALESCE(NULLIF(provider_payment_id,''),NULLIF(?,''))
                   WHERE id=? AND status IN ('pending','processing') AND credited_at IS NULL""",
                (now, now, now, payment_id, dep_id),
            )
            if cur.rowcount != 1:
                conn.rollback()
                current = get_deposit(order_id)
                if current and current[7] == "credited":
                    return 200, {"status": "already_credited"}
                return 409, {"status": "invalid_transition"}
            cur.execute(
                "UPDATE users SET balance=ROUND(COALESCE(balance,0)+?,2) WHERE id=?",
                (amount_uzs, user_id),
            )
            if cur.rowcount != 1:
                raise ValueError("user_missing")
            balance_after = cur.execute("SELECT COALESCE(balance,0) FROM users WHERE id=?", (user_id,)).fetchone()[0]
            cur.execute(
                """INSERT INTO wallet_transactions(user_id,type,amount,balance_after,job_id,description,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (user_id, "deposit", float(amount_uzs), balance_after, None,
                 "Payme orqali hamyon to‘ldirildi", now),
            )
            cur.execute("UPDATE wallet_deposits SET wallet_transaction_id=? WHERE id=?", (cur.lastrowid, dep_id))
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            if "provider_payment_id" in str(exc):
                log.error("payme: provider payment id conflict for deposit %s", order_id)
                return 409, {"status": "payment_id_conflict"}
            log.exception("payme: crediting deposit %s failed; rolled back", order_id)
            return 500, {"status": "temporary_error"}
        except Exception:
            conn.rollback()
            log.exception("payme: crediting deposit %s failed; rolled back", order_id)
            return 500, {"status": "temporary_error"}
        finally:
            conn.close()
        try:
            create_notification(
                user_id, "wallet_deposit", "Hamyon to‘ldirildi",
                f"Payme orqali {amount_uzs:,.0f} UZS hamyoningizga tushdi.", "/profile",
            )
        except Exception:
            log.exception("payme: notification failed for deposit %s", order_id)
        return 200, {"status": "credited"}

    # ------------------------------------------------ Payme HTTP calls
    def signed_request(cfg, params):
        body = {k: v for k, v in params.items() if v not in (None, "")}
        body["merchant_id"] = int(cfg["merchant_id"])
        body["signature"] = payme_signature(cfg["merchant_key"], body)
        return {"request": body}

    def create_payme_order(cfg, deposit_uuid, amount_minor):
        sep = "&" if "?" in cfg["response_url"] else "?"
        params = {
            "order_id": deposit_uuid,
            "order_desc": "FinJob hamyonini to‘ldirish",
            "amount": amount_minor,
            "currency": "UZS",
            "lifetime": cfg["lifetime"],
            "delayed": "N",  # one terminal callback per order => simple, deterministic lifecycle
            "server_callback_url": cfg["callback_url"],
            "response_url": f"{cfg['response_url']}{sep}{urlencode({'deposit': deposit_uuid})}",
            # `version` omitted on purpose: optional (default 1.0.1) and every extra signed parameter is
            # another thing that could change the signature string.
        }
        answer = _http_post_json(f"{cfg['base_url']}/api/checkout/url", signed_request(cfg, params))
        resp = (answer or {}).get("response") or {}
        if resp.get("response_status") != "success" or not resp.get("checkout_url"):
            raise RuntimeError(f"payme order rejected: code={resp.get('error_code')}")
        checkout = str(resp["checkout_url"])
        host = (urlsplit(checkout).hostname or "").lower()
        base_host = (urlsplit(cfg["base_url"]).hostname or "").lower()
        if urlsplit(checkout).scheme != "https" or not host or not (host == base_host or host.endswith(".payme.uz")):
            raise RuntimeError("payme returned an unexpected checkout host")
        # The creation-time payment_id is NOT trusted/stored: the docs do not promise it equals the id in later
        # callbacks, and enforcing it could reject a genuine approval. Only signed callback/status data sets it.
        return checkout, ""

    _last_reconcile = {}

    def reconcile(cfg, deposit_uuid):
        """Ask Payme for the order status (signed both ways). Network/format errors never raise."""
        import time
        now_m = time.monotonic()
        if now_m - _last_reconcile.get(deposit_uuid, -100.0) < 5.0:  # do not let polling hammer Payme
            return
        _last_reconcile[deposit_uuid] = now_m
        if len(_last_reconcile) > 5000:
            _last_reconcile.clear()
        try:
            answer = _http_post_json(
                f"{cfg['base_url']}/api/status/order_id",
                signed_request(cfg, {"order_id": deposit_uuid}),
            )
            resp = (answer or {}).get("response") or {}
            if resp.get("response_status") != "success":
                return
            if not verify_signature(cfg["merchant_key"], resp):
                log.error("payme: status response for %s failed signature check", deposit_uuid)
                return
            if str(resp.get("order_id", "")) != deposit_uuid:
                return
            apply_order_update(resp, "status_api", cfg)
        except Exception as exc:  # noqa: BLE001
            log.warning("payme: status check for %s failed: %s", deposit_uuid, type(exc).__name__)

    # ------------------------------------------------ user endpoints
    @app.route("/wallet/deposit-config")
    @auth
    def deposit_config():
        schema()
        cfg = load_config()
        return jsonify({
            "enabled": cfg["enabled"], "providers": ["payme"] if cfg["enabled"] else [],
            "currency": "UZS", "min_amount": cfg["min_uzs"], "max_amount": cfg["max_uzs"],
            "test_mode": bool(cfg["test_mode"]) if cfg["enabled"] else False,
        })

    @app.route("/wallet/deposits", methods=["POST"])
    @auth
    def create_deposit():
        schema()
        if enforce_block:
            blocked = enforce_block("full")
            if blocked:
                return blocked
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"msg": "So‘rov noto‘g‘ri"}), 400
        if "user_id" in data and str(data.get("user_id")) != str(request.uid):
            return jsonify({"msg": "Boshqa foydalanuvchi hamyonini to‘ldirib bo‘lmaydi"}), 403
        if str(data.get("provider", "payme")).lower() != "payme":
            return jsonify({"msg": "To‘lov usuli qo‘llab-quvvatlanmaydi"}), 400
        cfg = load_config()
        if not cfg["enabled"]:
            log.warning("payme disabled: %s", "; ".join(cfg["problems"]))
            return jsonify({"msg": "Payme orqali to‘ldirish hozircha mavjud emas"}), 503
        amount = _parse_amount(data.get("amount"))
        if amount is None or amount <= 0:
            return jsonify({"msg": "Summa butun son (UZS) bo‘lishi kerak"}), 400
        if amount < cfg["min_uzs"] or amount > cfg["max_uzs"]:
            return jsonify({"msg": f"Summa {cfg['min_uzs']:,} dan {cfg['max_uzs']:,} UZS gacha bo‘lishi kerak"}), 400

        open_count = db.q(
            "SELECT COUNT(*) FROM wallet_deposits WHERE user_id=? AND status IN ('pending','processing') AND expires_at>?",
            (request.uid, _iso(_now())),
        ).fetchone()[0]
        if open_count >= cfg["max_open"]:
            return jsonify({"msg": "Tugallanmagan to‘ldirishlar juda ko‘p. Birozdan keyin urinib ko‘ring"}), 429

        deposit_uuid = uuid.uuid4().hex
        now = _now()
        expires = now + datetime.timedelta(seconds=cfg["lifetime"])
        db.q(
            """INSERT INTO wallet_deposits(deposit_uuid,user_id,amount_uzs,amount_minor,currency,provider,status,is_test,
                                           created_at,expires_at)
               VALUES(?,?,?,?,'UZS','payme','pending',?,?,?)""",
            (deposit_uuid, request.uid, amount, uzs_to_tiyin(amount), 1 if cfg["test_mode"] else 0,
             _iso(now), _iso(expires)),
        ).close()
        try:
            checkout_url, payment_id = create_payme_order(cfg, deposit_uuid, uzs_to_tiyin(amount))
        except Exception as exc:  # noqa: BLE001
            log.error("payme: creating order for %s failed: %s", deposit_uuid, type(exc).__name__)
            db.q(
                "UPDATE wallet_deposits SET status='failed',cancelled_at=?,cancel_reason='checkout_creation_failed' "
                "WHERE deposit_uuid=? AND status='pending'",
                (_iso(_now()), deposit_uuid),
            ).close()
            return jsonify({"msg": "Payme bilan bog‘lanib bo‘lmadi. Keyinroq urinib ko‘ring"}), 502
        try:
            db.q(
                "UPDATE wallet_deposits SET checkout_url=?,provider_payment_id=NULLIF(?,'') WHERE deposit_uuid=?",
                (checkout_url, payment_id, deposit_uuid),
            ).close()
        except sqlite3.IntegrityError:
            db.q("UPDATE wallet_deposits SET checkout_url=? WHERE deposit_uuid=?", (checkout_url, deposit_uuid)).close()
        row = get_deposit(deposit_uuid)
        return jsonify({"msg": "ok", **public_view(row), "checkout_url": checkout_url}), 201

    @app.route("/wallet/deposits", methods=["GET"])
    @auth
    def list_deposits():
        schema()
        rows = db.q(
            f"SELECT {COLS} FROM wallet_deposits WHERE user_id=? ORDER BY id DESC LIMIT 50", (request.uid,)
        ).fetchall()
        return jsonify([public_view(r) for r in rows])

    @app.route("/wallet/deposits/<deposit_uuid>", methods=["GET"])
    @auth
    def deposit_status(deposit_uuid):
        schema()
        if not _UUID_RE.match(deposit_uuid):
            return jsonify({"msg": "To‘ldirish topilmadi"}), 404
        row = get_deposit(deposit_uuid)
        if not row or row[2] != request.uid:  # never reveal other users' deposits
            return jsonify({"msg": "To‘ldirish topilmadi"}), 404
        if row[7] in OPEN_STATUSES:
            cfg = load_config()
            if cfg["enabled"]:
                reconcile(cfg, deposit_uuid)
                row = get_deposit(deposit_uuid)
        view = public_view(row)
        if row[7] not in OPEN_STATUSES:
            view.pop("checkout_url", None)
        elif row[9]:
            view["checkout_url"] = row[9]
        return jsonify(view)

    # ------------------------------------------------ Payme-facing endpoints
    @app.route("/wallet/deposits/return", methods=["GET", "POST"])
    def deposit_return():
        """Browser lands here after Payme checkout. Purely a redirect: it NEVER changes state or credits."""
        cfg = load_config()
        target = cfg["frontend_return_url"]
        if not target:
            return jsonify({"msg": "not configured"}), 404
        dep = request.args.get("deposit", "")
        sep = "&" if "?" in target else "?"
        suffix = f"{sep}{urlencode({'payme_deposit': dep})}" if _UUID_RE.match(dep) else ""
        return redirect(target + suffix, code=303)

    @app.route("/payments/payme/callback", methods=["POST"])
    def payme_callback():
        schema()
        cfg = load_config()
        if not cfg["enabled"]:
            return jsonify({"status": "disabled"}), 503
        if cfg["ip_allowlist"] and request.remote_addr not in cfg["ip_allowlist"]:
            log.warning("payme: callback from non-allowlisted address rejected")
            return jsonify({"status": "forbidden"}), 403
        payload = request.get_json(silent=True)
        if isinstance(payload, dict) and isinstance(payload.get("response"), dict):
            payload = payload["response"]
        if not isinstance(payload, dict):
            return jsonify({"status": "bad_request"}), 400
        if not verify_signature(cfg["merchant_key"], payload):
            log.warning("payme: callback with invalid signature rejected")
            return jsonify({"status": "invalid_signature"}), 403
        status_code, body = apply_order_update(payload, "callback", cfg)
        return jsonify(body), status_code

    app.config["FINJOB_PAYME_APPLY"] = apply_order_update  # exposed for tests/tools only
