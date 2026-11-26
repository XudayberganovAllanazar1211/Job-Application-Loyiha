"""Payme wallet top-ups for FinJob.

Protocol: Payme "Payment API" documented at https://docs.payme.uz/api/ :
  * order creation   POST {base}/api/checkout/url   body {"request": {...}} -> {"response": {checkout_url, ...}}
  * order status     POST {base}/api/status/order_id body {"request": {...}} -> {"response": {order fields}}
  * server callback  POST (flat JSON object) to our `server_callback_url`; Payme retries until it gets HTTP 200
                     (2s, 1m, 5m, 10m, 1h, 24h) and never follows redirects.
  * signature        sha1(secret|v1|v2|...) over every non-empty parameter except `signature` (and the
                     test-mode diagnostic `response_signature_string`), values ordered by parameter name.
                     This mirrors the reference Python snippet on docs.payme.uz/api/building-signature.

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
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlencode, urlsplit

from flask import jsonify, redirect, request

PAYME_TEST_MERCHANT_ID = "4056281"  # public test merchant from docs.payme.uz/api/testing
PAYME_PUBLIC_TEST_KEYS = frozenset({"test", "testcredit"})  # public test keys from the same page
PAYME_HOST_SUFFIX = "payme.uz"
DEPOSIT_STATUSES = (
    "pending", "processing", "credited", "declined", "expired", "cancelled", "failed", "reversed",
)
OPEN_STATUSES = ("pending", "processing")
_UUID_RE = re.compile(r"^[0-9a-f]{32}$")
_DIGITS_RE = re.compile(r"^[0-9]{1,19}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-f]{40}$")


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


def _host(url):
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _is_http_url(url, https_only=False):
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    allowed = ("https",) if https_only else ("http", "https")
    return parts.scheme.lower() in allowed and bool(parts.hostname) and not parts.username and not parts.password


def _is_payme_host(host):
    return host == PAYME_HOST_SUFFIX or host.endswith("." + PAYME_HOST_SUFFIX)


# ---------------------------------------------------------------- configuration
_INT_SETTINGS = (
    ("lifetime", "PAYME_ORDER_LIFETIME_SECONDS", 3600),
    ("min_uzs", "PAYME_MIN_AMOUNT_UZS", 1000),
    ("max_uzs", "PAYME_MAX_AMOUNT_UZS", 50_000_000),
    ("max_open", "PAYME_MAX_OPEN_DEPOSITS", 5),
)


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
        "int_errors": [],
    }
    for key, env_name, default in _INT_SETTINGS:
        raw = str(env.get(env_name, "")).strip()
        if not raw:
            cfg[key] = default
            continue
        try:
            cfg[key] = int(raw)
        except ValueError:
            cfg[key] = default
            cfg["int_errors"].append(f"{env_name} must be a whole number")
    cfg["lifetime"] = max(300, min(86400, cfg["lifetime"]))
    cfg["problems"] = config_problems(cfg)
    cfg["enabled"] = not cfg["problems"]
    return cfg


def config_problems(cfg):
    """Explicit opt-in; anything ambiguous disables the integration (fail safe).

    Messages name the variable that is wrong but never echo a secret value.
    """
    problems = list(cfg.get("int_errors", []))
    live = not cfg["test_mode"]
    strict = live or cfg["production"]  # anything that can move real money needs https everywhere
    if not cfg["switch"]:
        problems.append("PAYME_ENABLED is not 1")
    if not cfg["test_mode_set"]:
        problems.append("PAYME_TEST_MODE must be set explicitly to 1 or 0")
    if not cfg["merchant_id"].isdigit():
        problems.append("PAYME_MERCHANT_ID missing/invalid (digits only)")
    if not cfg["merchant_key"]:
        problems.append("PAYME_MERCHANT_KEY missing")
    if not cfg["callback_url"]:
        problems.append("PAYME_CALLBACK_URL missing")
    elif not _is_http_url(cfg["callback_url"], https_only=strict):
        problems.append("PAYME_CALLBACK_URL must be an absolute " + ("https" if strict else "http(s)") + " URL")
    for name in ("response_url", "frontend_return_url"):
        env_name = "PAYME_" + name.upper()
        if not cfg[name]:
            problems.append(f"{env_name} missing")
        elif not _is_http_url(cfg[name], https_only=strict):
            problems.append(f"{env_name} must be an absolute " + ("https" if strict else "http(s)") + " URL")
    if not _is_http_url(cfg["base_url"], https_only=True):
        problems.append("PAYME_CHECKOUT_BASE_URL must be https")
    elif live and not _is_payme_host(_host(cfg["base_url"])):
        problems.append("live PAYME_CHECKOUT_BASE_URL must be on payme.uz")
    if uzs_to_tiyin(cfg["max_uzs"]) > PAYME_MAX_MINOR_AMOUNT:
        problems.append("PAYME_MAX_AMOUNT_UZS exceeds Payme's integer(12) amount field")
    if cfg["min_uzs"] <= 0 or cfg["max_uzs"] < cfg["min_uzs"]:
        problems.append("invalid min/max amount limits")
    if cfg["max_open"] < 1:
        problems.append("PAYME_MAX_OPEN_DEPOSITS must be at least 1")
    if cfg["production"] and cfg["test_mode"]:
        problems.append("test mode is refused when FINJOB_ENV=production")
    if live and cfg["merchant_id"] == PAYME_TEST_MERCHANT_ID:
        problems.append("live mode cannot use the public test merchant")
    if live and cfg["merchant_key"] in PAYME_PUBLIC_TEST_KEYS:
        problems.append("live mode cannot use a public test key")
    return problems


def config_summary(cfg):
    """Operator diagnostics. Never contains the merchant key; the merchant id is masked."""
    mid = cfg["merchant_id"]
    return {
        "enabled": cfg["enabled"],
        "switch": cfg["switch"],
        "test_mode": cfg["test_mode"],
        "production_env": cfg["production"],
        "merchant_id": ("*" * max(0, len(mid) - 4) + mid[-4:]) if mid else "",
        "merchant_key_configured": bool(cfg["merchant_key"]),
        "checkout_base_url": cfg["base_url"],
        "callback_url": cfg["callback_url"],
        "response_url": cfg["response_url"],
        "frontend_return_url": cfg["frontend_return_url"],
        "order_lifetime_seconds": cfg["lifetime"],
        "min_amount_uzs": cfg["min_uzs"],
        "max_amount_uzs": cfg["max_uzs"],
        "max_open_deposits": cfg["max_open"],
        "callback_ip_allowlist": list(cfg["ip_allowlist"]),
        "problems": list(cfg["problems"]),
    }


# ---------------------------------------------------------------- signature
def payme_signature_string(secret, params):
    """docs.payme.uz/api/building-signature: secret + all non-empty params sorted by name, '|' separated.

    Deliberately identical to the documented reference implementation: every parameter Payme sent is included
    (also fields FinJob does not use, e.g. additional_info, fee_oplata), 0 / "0" are kept, only '' and None are
    skipped, and `signature` / `response_signature_string` are excluded.
    """
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
    given = str(payload.get("signature", "") or "").strip().lower()
    if not secret or not _SIGNATURE_RE.match(given):
        return False
    # Compare as bytes: secrets.compare_digest raises TypeError on non-ASCII str (would be a 500 on hostile input).
    return secrets.compare_digest(payme_signature(secret, payload).encode("utf-8"), given.encode("ascii"))


# ---------------------------------------------------------------- Payme HTTP calls
class PaymeAPIError(Exception):
    """A Payme API call did not produce a usable answer. `reason` is safe to log (no secrets)."""

    def __init__(self, reason, error_code=None):
        super().__init__(reason)
        self.reason = reason
        self.error_code = error_code


def _http_post_json(url, body, timeout=15):
    """Server-to-server call to Payme. Isolated so tests can mock it (no real requests in tests)."""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "User-Agent": "FinJob-Payme/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https enforced by config)
            raw = resp.read(1_000_000)
    except urllib.error.HTTPError as exc:
        raw = exc.read(1_000_000)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise PaymeAPIError(f"http_{exc.code}") from None
    return json.loads(raw.decode("utf-8"))


def signed_request(cfg, params):
    body = {k: v for k, v in params.items() if v not in (None, "")}
    body["merchant_id"] = int(cfg["merchant_id"])
    body["signature"] = payme_signature(cfg["merchant_key"], body)
    return {"request": body}


def _call(cfg, path, params, timeout):
    try:
        answer = _http_post_json(f"{cfg['base_url']}{path}", signed_request(cfg, params), timeout=timeout)
    except PaymeAPIError:
        raise
    except (TimeoutError, OSError) as exc:  # URLError, socket.timeout, connection reset ...
        raise PaymeAPIError("network_" + type(exc).__name__) from None
    except ValueError:
        raise PaymeAPIError("invalid_json") from None
    resp = answer.get("response") if isinstance(answer, dict) else None
    if not isinstance(resp, dict):
        raise PaymeAPIError("invalid_envelope")
    if resp.get("response_status") != "success":
        code = resp.get("error_code")
        raise PaymeAPIError(f"payme_error_{code}" if code not in (None, "") else "payme_failure", code)
    return resp


def is_allowed_checkout_url(url, base_url):
    try:
        parts = urlsplit(str(url))
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return False
    return host == _host(base_url) or _is_payme_host(host)


def order_request_params(cfg, deposit_uuid, amount_minor):
    sep = "&" if "?" in cfg["response_url"] else "?"
    return {
        "order_id": deposit_uuid,
        "order_desc": "FinJob hamyonini to‘ldirish",
        "amount": int(amount_minor),
        "currency": "UZS",
        "lifetime": cfg["lifetime"],
        "delayed": "N",  # one terminal callback per order => simple, deterministic lifecycle
        "server_callback_url": cfg["callback_url"],
        "response_url": f"{cfg['response_url']}{sep}{urlencode({'deposit': deposit_uuid})}",
        # `version` omitted on purpose: optional (default 1.0.1).
    }


def create_checkout(cfg, deposit_uuid, amount_minor, timeout=15):
    """Create the hosted Payme order and return the validated checkout URL (raises PaymeAPIError)."""
    resp = _call(cfg, "/api/checkout/url", order_request_params(cfg, deposit_uuid, amount_minor), timeout)
    checkout = resp.get("checkout_url")
    if not checkout or not isinstance(checkout, str):
        raise PaymeAPIError("missing_checkout_url")
    if not is_allowed_checkout_url(checkout, cfg["base_url"]):
        raise PaymeAPIError("unexpected_checkout_host")
    # The creation-time payment_id is NOT trusted/stored: only signed callback/status data sets it.
    return checkout


def fetch_order_status(cfg, deposit_uuid, timeout=8):
    """Signed status request; returns the response only if Payme's signature on it is valid."""
    resp = _call(cfg, "/api/status/order_id", {"order_id": deposit_uuid}, timeout)
    if not verify_signature(cfg["merchant_key"], resp):
        raise PaymeAPIError("status_signature_invalid")
    if str(resp.get("order_id", "")) != deposit_uuid:
        raise PaymeAPIError("status_order_mismatch")
    return resp


def _parse_amount(value):
    """Strict non-negative integer from int or digit-string; None if anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and _DIGITS_RE.match(value.strip()):
        return int(value.strip())
    return None


# Transaction types (docs.payme.uz/api/order-parameters, `tran_type`, "Supported values"): purchase, verification,
# p2p credit, p2p transfer, settlement, reverse. FinJob only ever creates `purchase` orders.
PAYME_PURCHASE_TRAN_TYPE = "purchase"
# For a `reversed` order the docs do not say whether the original order keeps tran_type `purchase` or reports
# `reverse`; both are accepted there (a reversal never adds money, it only closes or flags a deposit).
_REVERSED_TRAN_TYPES = frozenset({"purchase", "reverse"})


def _norm(value):
    """Lower-cased, stripped string for enum-like fields; '' for missing/None or for non-scalar JSON values."""
    if value is None or isinstance(value, (dict, list, bool)):
        return ""
    return str(value).strip().lower()


def tran_type_problem(payload, order_status):
    """Outcome name if `tran_type` is wrong for this order status, else None.

    `approved` (the only status that credits a wallet) requires tran_type to be present and equal to "purchase"
    (trimmed, case-insensitive).
    Other statuses never credit; there a missing tran_type is tolerated, but a present value that does not fit a
    FinJob purchase order (e.g. "verification", "p2p transfer") is inconsistent and is refused.
    """
    tran_type = _norm(payload.get("tran_type"))
    if order_status == "approved":
        if not tran_type:
            return "tran_type_missing"
        return None if tran_type == PAYME_PURCHASE_TRAN_TYPE else "tran_type_mismatch"
    if not tran_type:
        return None
    allowed = _REVERSED_TRAN_TYPES if order_status == "reversed" else {PAYME_PURCHASE_TRAN_TYPE}
    return None if tran_type in allowed else "tran_type_mismatch"


def approved_payment_problem(payload, expected_minor):
    """Outcome name if an `approved` order's charged amount/currency is not exactly what FinJob expects, else None.

    docs.payme.uz/api/order-parameters: `approved` = "funds are held on the payer's account"; `actual_amount` =
    "The actual amount held or charged from card"; `actual_currency` = "The actual currency authorized from card".
    The docs mark no response field as mandatory, but every documented approved example carries both fields and a
    payment that was really held has a held amount. So for crediting they are REQUIRED: missing, malformed or
    different values never credit and are flagged for manual review (a later correct callback can still credit).
    """
    actual_raw = payload.get("actual_amount")
    if actual_raw is None or (isinstance(actual_raw, str) and not actual_raw.strip()):
        return "actual_amount_missing"
    actual = _parse_amount(actual_raw)
    if actual is None:
        return "actual_amount_invalid"
    if actual != expected_minor:
        return "actual_amount_mismatch"
    actual_cur = payload.get("actual_currency")
    if actual_cur is None or (isinstance(actual_cur, str) and not actual_cur.strip()):
        return "actual_currency_missing"
    if not isinstance(actual_cur, str) or actual_cur.strip().upper() != "UZS":
        return "actual_currency_mismatch"
    return None


def _payload_says_test(payload):
    """True when Payme marks the transaction as a test one (additional_info is a JSON *string* per the docs)."""
    info = payload.get("additional_info")
    if isinstance(info, str) and info.strip():
        try:
            info = json.loads(info)
        except ValueError:
            return False
    return isinstance(info, dict) and info.get("is_test") is True


def register_payme_routes(app, db, auth, create_notification, enforce_block=None, admin_required=None):
    log = app.logger

    # ------------------------------------------------------------ schema
    def ensure_schema():
        """Idempotent: only CREATE ... IF NOT EXISTS; never alters or deletes existing FinJob data."""
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
        """Create the tables on first use of each database file (also covers test/alternate DBs)."""
        if db.db_name not in _ready:
            ensure_schema()
            _ready.add(db.db_name)

    schema()

    startup_cfg = load_config()
    if startup_cfg["enabled"]:
        log.info("payme: enabled (test_mode=%s)", startup_cfg["test_mode"])
    elif startup_cfg["switch"]:
        log.warning("payme: PAYME_ENABLED=1 but configuration is incomplete: %s", "; ".join(startup_cfg["problems"]))

    COLS = (
        "id,deposit_uuid,user_id,amount_uzs,amount_minor,currency,provider_payment_id,status,is_test,"
        "checkout_url,created_at,expires_at,paid_at,credited_at,cancelled_at,cancel_reason,review_required,reversed_at"
    )

    def public_view(row):
        return {
            "deposit_id": row[1], "amount": row[3], "currency": row[5], "provider": "payme",
            # `deposit_status` duplicates `status` because the frontend api() helper overwrites a body's `status`
            # with the HTTP status code.
            "status": row[7], "deposit_status": row[7], "test": bool(row[8]), "created_at": row[10], "expires_at": row[11],
            "paid_at": row[12], "credited_at": row[13], "cancelled_at": row[14],
            "cancel_reason": row[15] or "", "under_review": bool(row[16]), "reversed_at": row[17],
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
        if bool(row[8]) != bool(cfg["test_mode"]):
            return 400, {"status": "mode_mismatch"}
        if not cfg["test_mode"] and _payload_says_test(payload):
            return 400, {"status": "test_payment_in_live_mode"}
        if str(payload.get("currency", "")).strip().upper() != "UZS":
            return 400, {"status": "currency_mismatch"}
        amount = _parse_amount(payload.get("amount"))
        if amount is None or amount != amount_minor:
            return 400, {"status": "amount_mismatch"}

        if str(payload.get("response_status", "")).strip().lower() != "success":
            return 400, {"status": "response_status_not_success"}
        new_status = _norm(payload.get("order_status"))
        tran_problem = tran_type_problem(payload, new_status)
        if tran_problem:
            return 400, {"status": tran_problem}
        payment_id = str(payload.get("payment_id", "") or "").strip()
        stored_payment_id = row[6] or ""
        if payment_id and not _DIGITS_RE.match(payment_id):
            return 400, {"status": "bad_payment_id"}
        if payment_id and stored_payment_id and payment_id != stored_payment_id:
            return 400, {"status": "payment_id_mismatch"}
        now = _iso(_now())

        if new_status == "approved":
            # Checked before the idempotent "already_credited" answer on purpose: an inconsistent approval is
            # always surfaced for review, even for a deposit that is already credited.
            payment_problem = approved_payment_problem(payload, amount_minor)
            if payment_problem:
                return 400, {"status": payment_problem}
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
            return credit_deposit(dep_id, user_id, amount_uzs, order_id, payment_id, now)

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
            if status in OPEN_STATUSES:
                # Approved and fully reversed before FinJob credited anything: the payer got the money back and
                # the wallet was never touched, so there is nothing to undo.
                return mark_terminal(dep_id, "reversed", payment_id, payload, now)
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
        operator-fixable config problems answer non-200 so retries continue. A 200 never means "credited":
        the body's `status` says what actually happened.
        """
        order_id = str(payload.get("order_id", "")).strip()
        try:
            code, body = _apply(payload, source, cfg)
        except sqlite3.Error:
            log.exception("payme: database error while applying %s for %s", source, order_id[:40])
            code, body = 500, {"status": "temporary_error"}
        outcome = body.get("status", "")
        if code != 200 and outcome not in RETRYABLE:
            row = get_deposit(order_id) if _UUID_RE.match(order_id) else None
            if row:
                flag_review(row[0], f"callback not applied: {outcome}")
            log.error("payme: signed %s not applied (%s) for order %s: flagged for manual review",
                      source, outcome, order_id[:40])
            record_event(order_id, source, payload, code, outcome, True)
            return 200, {"status": outcome, "flagged": True}
        record_event(order_id, source, payload, code, outcome, False)
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
                "reversed_at=CASE WHEN ?='reversed' THEN ? ELSE reversed_at END,"
                "provider_payment_id=COALESCE(NULLIF(provider_payment_id,''),NULLIF(?,'')),last_event_at=? "
                "WHERE id=? AND status IN ('pending','processing')",
                (new_status, new_status, now, reason or new_status, new_status, now, payment_id, now, dep_id),
            ).close()
        except sqlite3.IntegrityError:
            return 409, {"status": "payment_id_conflict"}
        return 200, {"status": new_status}

    class _UserMissing(Exception):
        pass

    def credit_deposit(dep_id, user_id, amount_uzs, order_id, payment_id, now):
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
                raise _UserMissing()
            balance_after = cur.execute("SELECT COALESCE(balance,0) FROM users WHERE id=?", (user_id,)).fetchone()[0]
            cur.execute(
                """INSERT INTO wallet_transactions(user_id,type,amount,balance_after,job_id,description,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (user_id, "deposit", float(amount_uzs), balance_after, None,
                 "Payme orqali hamyon to‘ldirildi", now),
            )
            cur.execute("UPDATE wallet_deposits SET wallet_transaction_id=? WHERE id=?", (cur.lastrowid, dep_id))
            conn.commit()
        except _UserMissing:
            conn.rollback()
            log.error("payme: user for deposit %s no longer exists; not credited", order_id)
            return 409, {"status": "user_missing"}
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            if "provider_payment_id" in str(exc):
                log.error("payme: provider payment id conflict for deposit %s", order_id)
                return 409, {"status": "payment_id_conflict"}
            log.exception("payme: crediting deposit %s failed; rolled back", order_id)
            return 500, {"status": "temporary_error"}
        except Exception:  # noqa: BLE001 - locked DB, disk errors ...: roll back and let Payme retry
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
        except Exception:  # noqa: BLE001
            log.exception("payme: notification failed for deposit %s", order_id)
        return 200, {"status": "credited"}

    # ------------------------------------------------ status reconciliation
    _last_reconcile = {}

    def reconcile(cfg, deposit_uuid):
        """Ask Payme for the order status (signed both ways). Network/format errors never raise."""
        now_m = time.monotonic()
        if now_m - _last_reconcile.get(deposit_uuid, -100.0) < 5.0:  # do not let polling hammer Payme
            return
        _last_reconcile[deposit_uuid] = now_m
        if len(_last_reconcile) > 5000:
            _last_reconcile.clear()
        try:
            resp = fetch_order_status(cfg, deposit_uuid)
        except PaymeAPIError as exc:
            log.warning("payme: status check for %s failed: %s", deposit_uuid, exc.reason)
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("payme: status check for %s failed: %s", deposit_uuid, type(exc).__name__)
            return
        apply_order_update(resp, "status_api", cfg)

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
            "order_lifetime_seconds": cfg["lifetime"],
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
            return jsonify({"msg": "Payme orqali to‘ldirish hozircha mavjud emas", "code": "payme_disabled"}), 503
        amount = _parse_amount(data.get("amount"))
        if amount is None or amount <= 0:
            return jsonify({"msg": "Summa butun son (UZS) bo‘lishi kerak", "code": "invalid_amount"}), 400
        if amount < cfg["min_uzs"] or amount > cfg["max_uzs"]:
            return jsonify({"msg": f"Summa {cfg['min_uzs']:,} dan {cfg['max_uzs']:,} UZS gacha bo‘lishi kerak",
                            "code": "amount_out_of_range"}), 400

        open_count = db.q(
            "SELECT COUNT(*) FROM wallet_deposits WHERE user_id=? AND status IN ('pending','processing') AND expires_at>?",
            (request.uid, _iso(_now())),
        ).fetchone()[0]
        if open_count >= cfg["max_open"]:
            return jsonify({"msg": "Tugallanmagan to‘ldirishlar juda ko‘p. Birozdan keyin urinib ko‘ring",
                            "code": "too_many_open"}), 429

        deposit_uuid = uuid.uuid4().hex
        amount_minor = uzs_to_tiyin(amount)
        now = _now()
        expires = now + datetime.timedelta(seconds=cfg["lifetime"])
        db.q(
            """INSERT INTO wallet_deposits(deposit_uuid,user_id,amount_uzs,amount_minor,currency,provider,status,is_test,
                                           created_at,expires_at)
               VALUES(?,?,?,?,'UZS','payme','pending',?,?,?)""",
            (deposit_uuid, request.uid, amount, amount_minor, 1 if cfg["test_mode"] else 0,
             _iso(now), _iso(expires)),
        ).close()
        try:
            checkout_url = create_checkout(cfg, deposit_uuid, amount_minor)
        except Exception as exc:  # noqa: BLE001
            reason = exc.reason if isinstance(exc, PaymeAPIError) else type(exc).__name__
            log.error("payme: creating order for %s failed: %s", deposit_uuid, reason)
            db.q(
                "UPDATE wallet_deposits SET status='failed',cancelled_at=?,cancel_reason='checkout_creation_failed' "
                "WHERE deposit_uuid=? AND status='pending'",
                (_iso(_now()), deposit_uuid),
            ).close()
            return jsonify({"msg": "Payme bilan bog‘lanib bo‘lmadi. Keyinroq urinib ko‘ring",
                            "code": "checkout_failed"}), 502
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
        if row[7] in OPEN_STATUSES and not row[16]:  # flagged deposits wait for an operator, not for polling
            cfg = load_config()
            if cfg["enabled"] and bool(row[8]) == bool(cfg["test_mode"]):
                reconcile(cfg, deposit_uuid)
                row = get_deposit(deposit_uuid)
        view = public_view(row)
        if row[7] in OPEN_STATUSES and row[9] and not row[16]:
            view["checkout_url"] = row[9]
        return jsonify(view)

    # ------------------------------------------------ operator endpoints (read-only)
    if admin_required is not None:
        @app.route("/admin/payme/diagnostics")
        @admin_required
        def payme_diagnostics():
            schema()
            counts = db.q("SELECT status, COUNT(*) FROM wallet_deposits GROUP BY status").fetchall()
            review = db.q("SELECT COUNT(*) FROM wallet_deposits WHERE review_required=1").fetchone()[0]
            return jsonify({
                "config": config_summary(load_config()),
                "deposits_by_status": {s: c for s, c in counts},
                "review_required": review,
            })

        @app.route("/admin/wallet-deposits")
        @admin_required
        def admin_wallet_deposits():
            schema()
            only_review = request.args.get("review") == "1"
            rows = db.q(
                "SELECT deposit_uuid,user_id,amount_uzs,status,is_test,provider_payment_id,review_required,review_note,"
                "created_at,credited_at,reversed_at,last_event_at FROM wallet_deposits "
                + ("WHERE review_required=1 " if only_review else "") + "ORDER BY id DESC LIMIT 100"
            ).fetchall()
            keys = ("deposit_id", "user_id", "amount", "status", "test", "provider_payment_id", "review_required",
                    "review_note", "created_at", "credited_at", "reversed_at", "last_event_at")
            return jsonify([dict(zip(keys, r)) for r in rows])

    # ------------------------------------------------ Payme-facing endpoints
    @app.route("/wallet/deposits/return", methods=["GET", "POST"])
    def deposit_return():
        """Browser lands here after Payme checkout. Purely a redirect: it NEVER changes state or credits."""
        cfg = load_config()
        target = cfg["frontend_return_url"]
        if not target or not _is_http_url(target):
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
        if payload is None and request.form:
            payload = request.form.to_dict(flat=True)  # Payme documents JSON, but form posts are accepted too
        if isinstance(payload, dict) and "signature" not in payload and isinstance(payload.get("response"), dict):
            payload = payload["response"]
        if not isinstance(payload, dict):
            return jsonify({"status": "bad_request"}), 400
        if not verify_signature(cfg["merchant_key"], payload):
            log.warning("payme: callback with missing/invalid signature rejected")
            return jsonify({"status": "invalid_signature"}), 403
        status_code, body = apply_order_update(payload, "callback", cfg)
        return jsonify(body), status_code

    app.config["FINJOB_PAYME_APPLY"] = apply_order_update  # exposed for tests/tools only
