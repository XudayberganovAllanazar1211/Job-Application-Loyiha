# Payme wallet top-ups

FinJob lets a user top up their FinJob wallet with real UZS through Payme's hosted checkout.
Payme is used **only** for wallet deposits. Jobs are paid from the wallet balance (existing escrow flow).

> **Status: implemented and tested against mocks only.** It has not been exercised against a real Payme
> test or live merchant. See "Before going live" and "Known limitations".

## Which Payme API this uses

`docs.payme.uz` currently documents the **Payment API** (hosted checkout via `POST {base}/api/checkout/url`,
signed server callbacks, `POST {base}/api/status/order_id`). It does **not** document the classic
JSON-RPC Merchant API (`CheckPerformTransaction`, `CreateTransaction`, `PerformTransaction`, ...). This integration
implements what docs.payme.uz documents. The legacy JSON-RPC Merchant API is **not obsolete** and is still publicly
documented; we simply chose the hosted Checkout API. **Our merchant account must be provisioned for the hosted
Checkout (Payment) API.** If it is provisioned only for the JSON-RPC Merchant API, this module will not work and a
different adapter is needed. Confirm with Payme before any activation (questions at the end of this file).

## Architecture

```
Profile.jsx --POST /wallet/deposits--> backend: INSERT wallet_deposits(pending)
                                        backend --signed POST /api/checkout/url--> Payme  (returns checkout_url)
browser <-- checkout_url -- backend
browser --------------------------------> Payme hosted checkout (card entry happens only at Payme)
Payme --signed POST /payments/payme/callback--> backend: verify signature, validate, credit wallet once
browser <-- redirect to PAYME_RESPONSE_URL --> /wallet/deposits/return --303--> frontend /profile?payme_deposit=<id>
frontend --GET /wallet/deposits/<id>--> backend (optionally asks Payme /api/status/order_id, signed) --> status
```

Rules enforced by the code:

* A wallet is credited **only** from an order with `order_status = approved` whose signature verifies, delivered
  by the server callback or by a signed answer to our own status request. The browser return URL never changes state.
* Crediting is one database transaction (`BEGIN IMMEDIATE`): conditional `UPDATE wallet_deposits ... WHERE status IN
  ('pending','processing') AND credited_at IS NULL`, balance update, `wallet_transactions` row (`type='deposit'`),
  back-reference. Any failure rolls everything back; Payme then retries and the retry succeeds.
* Repeated or concurrent callbacks are idempotent (the conditional update matches at most once).
* Amounts are integers. Deposit amount in whole UZS is validated by the backend; the amount sent to Payme is
  `uzs_to_tiyin(amount_uzs)` = `amount_uzs * 100` (UZS amounts are integer minor units, tiyin, no decimal separator: `100020` = 1000 UZS 20 tiyin). Example: user enters 100 000 UZS, Payme gets `10000000`, callback `amount` and `actual_amount` must both equal the stored `amount_minor` (10 000 000), and exactly 100 000 UZS is credited. FinJob values (`users.balance`, `wallet_transactions`, API, UI, `wallet_deposits.amount_uzs`) are always UZS; Payme values (`wallet_deposits.amount_minor`, request/callback `amount`) are always tiyin. `uzs_to_tiyin()` in `payme.py` is the only conversion point and the wallet is credited from `amount_uzs`, never from a Payme value.

### Database

New table `wallet_deposits` (created on first use, never touches `payments`, no `job_id`):
`deposit_uuid` (UNIQUE, = Payme `order_id`), `user_id`, `amount_uzs`, `amount_minor`, `currency` (CHECK `UZS`),
`provider` (CHECK `payme`), `provider_payment_id` (UNIQUE per provider), `status`
(`pending|processing|credited|declined|expired|cancelled|failed|reversed`), `is_test`, `checkout_url`,
`wallet_transaction_id`, `review_required`/`review_note`, timestamps (`created_at`, `expires_at`,
`provider_created_at`, `paid_at`, `credited_at`, `cancelled_at`, `cancel_reason`, `reversed_at`, `last_event_at`).
No card numbers or CVV are ever received or stored.
`users.balance` and `wallet_transactions` are unchanged (balance stays `REAL` with 2-decimal rounding; deposits are
whole-UZS integers so no new floating-point arithmetic is introduced).

### Endpoints

| Method / path | Auth | Purpose |
|---|---|---|
| `GET /wallet/deposit-config` | JWT | enabled flag, limits, test-mode flag (no secrets) |
| `POST /wallet/deposits` | JWT | create pending deposit `{amount, provider:"payme"}` -> `checkout_url` |
| `GET /wallet/deposits` | JWT | own deposit history |
| `GET /wallet/deposits/<id>` | JWT, owner only (404 otherwise) | status; reconciles with Payme if still open and not under review |
| `GET|POST /wallet/deposits/return` | none | browser redirect to the frontend; never credits |
| `POST /payments/payme/callback` | Payme signature | server-to-server result (JSON; form-encoded also accepted) |
| `GET /admin/payme/diagnostics` | admin | configuration problems (no secrets, merchant id masked), deposit counts |
| `GET /admin/wallet-deposits[?review=1]` | admin | latest deposits / review queue (read-only) |

Deposit objects carry both `status` and an identical `deposit_status`: the frontend `api()` helper overwrites a
body's `status` with the HTTP status code, so the UI reads `deposit_status`. `under_review: true` means an operator
must look at it; the UI stops polling and never shows success for it.

### Callback handling summary

| Payme `order_status` | Local transition |
|---|---|
| `approved` | `pending/processing` -> `credited` (+wallet, +history). Already `credited` -> 200 idempotent. Any other state -> deposit flagged `review_required`, answered 200, **no credit** |
| `declined`, `expired` | `pending/processing` -> same status. Repeats -> 200. After `credited` -> flagged, 200, no change |
| `created`, `processing` | informational |
| `reversed` | `credited` -> `reversed`, flagged `review_required`; wallet is **not** auto-debited. `pending/processing` -> `reversed` (nothing was credited, nothing to undo) |

In live mode a callback whose `additional_info` says `"is_test": true` is never credited (`test_payment_in_live_mode`, flagged).

**HTTP contract** (docs.payme.uz/api/callbacks: 200 = processed; anything else is retried at 2s, 1m, 5m, 10m, 1h, 24h;
redirects are not followed, we never redirect):

| Situation | Answer | Why |
|---|---|---|
| Credited, duplicate/already credited, declined/expired noted, stale `created`/`processing` | 200 | processed |
| Signed callback we handled but did not apply: late `approved` after declined/expired/cancelled, `approved` with non-zero `reversal_amount`, partial reversal after credit, amount/actual_amount/currency/payment_id mismatch, unknown order, unknown status, `response_status != success` | **200** with `"flagged": true` | retrying the identical callback can never succeed; the deposit is set `review_required=1` with a note and an audit row is written |
| Wrong `merchant_id`, test/live mode mismatch | 400 | operator-fixable configuration; keep Payme retrying |
| Temporary database failure while crediting (rolled back) | 500 | Payme retries and the retry credits once |
| Integration disabled / misconfigured | 503 | retry after configuration is fixed |
| Invalid or missing signature, non-allowlisted IP | 403 | not from Payme |
| Not JSON | 400 | |

Audit trail: table `wallet_deposit_events` gets one row per callback/status-API result (`deposit_uuid`, `source`,
`order_status`, `outcome`, `http_status`, `flagged`, `provider_payment_id`, `amount`, `created_at`). No card data,
signature or raw payload is stored. Review queue: `SELECT * FROM wallet_deposits WHERE review_required=1`.
A flagged deposit still in `pending` can still be credited by a later correct callback.
Orders are created with `delayed=N` so each order has one terminal result.

## Configuration

See `backend/.env.example`. The integration is **disabled** (503) unless all of these hold:

`PAYME_ENABLED=1`, `PAYME_TEST_MODE` explicitly `1` or `0`, `PAYME_MERCHANT_ID`, `PAYME_MERCHANT_KEY`,
`PAYME_CALLBACK_URL`, `PAYME_RESPONSE_URL`, `PAYME_FRONTEND_RETURN_URL`.
Additionally (all enforced by `load_config()`, problems listed by `GET /admin/payme/diagnostics` and
`python payme_sandbox_check.py --config`):

* numeric settings must be whole numbers (a typo disables the integration instead of silently using a default);
* URLs must be absolute `http(s)` URLs without credentials; `PAYME_CHECKOUT_BASE_URL` must be `https`;
* test mode is refused when `FINJOB_ENV=production`;
* live mode (`PAYME_TEST_MODE=0`) or `FINJOB_ENV=production` requires `https` for the callback, response and
  frontend return URLs;
* live mode refuses the public test merchant `4056281`, the public test keys `test`/`testcredit`, and any checkout
  host outside `payme.uz`;
* a deposit created in test mode cannot be completed in live mode and vice versa.

## Testing a deposit (Payme sandbox)

**Status on 2026-11-25:** the public test merchant from docs.payme.uz/api/testing (`4056281` / key `test`) is
rejected by `https://pay.payme.uz` with `error_code 1014 "Invalid signature"`, even for the documentation's own
verbatim example request. FinJob's signature code is identical to the documented reference snippet, so a real sandbox
test needs **test credentials from your own Payme merchant cabinet** (or from Payme support).

1. Put your cabinet's test merchant id and payment key in `backend/.env` with `PAYME_ENABLED=1`, `PAYME_TEST_MODE=1`.
2. `cd backend && python payme_sandbox_check.py` — creates one test order with the real API and verifies Payme's
   signature on the status answer. `payme_error_1014` here means the id/key pair is wrong. Nothing is credited.
3. Expose the backend over HTTPS (e.g. a tunnel) and set `PAYME_CALLBACK_URL`/`PAYME_RESPONSE_URL` to it. Payme must
   be able to reach the callback (its servers call from `54.154.216.60`, `3.75.125.89`).
4. Log in, open the profile wallet, press "Walletni to'ldirish", enter e.g. 10 000 UZS, pay with a test card from
   docs.payme.uz/api/testing.
5. Expect: redirect back to `/profile`, status "tasdiqlandi", balance +10 000, one `deposit` history row, one
   `credited` row in `wallet_deposit_events`.
6. Automated tests (`python -m unittest test_suite`, `npm test` in `frontend/`) never contact Payme.

## Before going live (merchant-side checklist)

* Confirm with Payme which API your merchant is provisioned for (Payment API vs classic JSON-RPC Merchant API).
* Contract/approval: confirm in writing that your merchant category and contract allow **crediting a
  stored-value wallet and holding customer funds in escrow**. A working API integration is not legal approval of
  stored balances, escrow, or later payouts; get legal/compliance advice for Uzbekistan.
* In the merchant cabinet obtain the live merchant id and payment secret key; register the callback URL and
  allow Payme's callback IPs through your firewall.
* Confirm signature behaviour (and the tiyin amount shown on the Payme page) with a test payment, then repeat with a minimal
  live payment.
* Set `FINJOB_ENV=production`, `PAYME_TEST_MODE=0`, live id/key, https URLs, `PAYME_ENABLED=1`. Put secrets in the
  deployment environment only (`.env` is git-ignored).
* Run behind HTTPS; decide on a reconciliation routine for `review_required = 1` deposits (below).

## Commission (2%) and existing databases

Fresh installs now seed `platform_settings.commission_percent` with **2** (code fallback also 2). A deposit never
charges a commission; commission applies only when escrow is released to a worker. **Existing databases are not
changed**: they keep their stored value (the old default was 10). To move a deployed database to 2%, either use the
admin endpoint `PATCH /admin/settings/commission` with `{"commission_percent": 2}` (audited), or run
`UPDATE platform_settings SET value='2' WHERE key='commission_percent';`. Payments already held in escrow are
released with the percentage in force at release time.

## Known limitations / not implemented

* **Real card withdrawals are not implemented.** `/wallet/withdraw` still only debits the FinJob balance (simulated).
  A real payout integration (e.g. Payme payouts with a card token) is a separate project.
* Reversals/chargebacks of an already credited deposit are flagged (`status=reversed`, `review_required=1`) but the
  wallet is not auto-debited, because the money may already be spent. There is no admin UI page yet; use
  `GET /admin/wallet-deposits?review=1` or `SELECT * FROM wallet_deposits WHERE review_required=1`.
* Admin user deletion is refused (409) for users with pending, credited, reversed or flagged Payme deposits, so
  financial records are kept; block such accounts instead.
* `PAYME_CALLBACK_IP_ALLOWLIST` compares `request.remote_addr`; behind a reverse proxy that is the proxy's address,
  so leave it empty there (the signature check is the real protection) or configure the proxy to pass the client IP.
* An `approved` result arriving after a local `declined`/`expired` state is rejected and flagged (money may have been
  taken at Payme); resolve manually with Payme.
* Click direct job payments (`/payments/create/<job>`) and the dummy/escrow endpoints are untouched. Click still
  exists as a direct-pay path when Click credentials are set; if you want a strict wallet-only model, disable it
  separately. The dummy payment endpoint only moves existing wallet balance into escrow; it cannot create money.
  `/admin/wallet/<id>` (admin test top-up) still exists: remove or restrict it before production.
* Signature digests printed in the Payme docs do not reproduce from the strings printed next to them, and the public
  test merchant currently rejects even the docs' own example request (see "Testing"). The signature code matches the
  documented reference snippet byte for byte (unit-tested against an independent copy of it), but acceptance by
  Payme's servers is unproven until `payme_sandbox_check.py` passes with your cabinet's test credentials.
* Amount unit: confirmed by you from the official docs as integer tiyin; implemented as a fixed constant. Still worth a one-line confirmation from Payme (question 2).
* SQLite remains the database; a PostgreSQL migration branch exists in the repo but is not integrated here.

## Audit log (backend/payme.py)

Confirmed and fixed:

1. `secrets.compare_digest` raised `TypeError` on a non-ASCII `signature` (HTTP 500 on hostile input). Now compares UTF-8 bytes; returns 403.
2. Callbacks never checked `response_status`. Now anything other than `success` is rejected (400).
3. A creation-time `payment_id` was stored and enforced; the docs do not promise it equals the id in later callbacks, so a genuine approval could have been rejected. It is no longer stored; only signed callback/status data sets it (still unique, still must stay consistent afterwards).
4. `approved` with a non-zero `reversal_amount` is not credited and is flagged for review (docs only define `reversed` as a full reversal; partial behaviour is unclear).
5. The optional `version` request parameter is no longer sent (it would be part of the signed string for no benefit).
6. The status endpoint call is throttled to once per 5 s per deposit so UI polling cannot hammer Payme.

Second audit (2026-11-25), confirmed and fixed:

7. Frontend: `api()` overwrites a response body's `status` with the HTTP code, so the return-from-Payme screen read
   `200` instead of `credited` and stopped polling after one request: a successful payment was never shown. The
   backend now also returns `deposit_status`, which the UI reads (found by a browser end-to-end run).
8. Frontend: under `React.StrictMode` (dev) the first effect run removed `?payme_deposit` and was then cancelled, so
   no status was ever shown in development. The id is now read once into state.
9. `reversed` for a deposit that was never credited was rejected as an invalid transition and the deposit stayed
   `pending` forever; it is now closed as `reversed` without touching the wallet.
10. Admin user deletion crashed with HTTP 500 (foreign-key violation) for any user with a Payme deposit.
11. Config: non-numeric limits silently fell back to defaults; live mode accepted the public test key `test` and a
    non-Payme checkout host; production accepted `http` return URLs; URL values were not validated.
12. Payme API errors were logged only as `RuntimeError`; the Payme `error_code` is now logged (never the key).
    Network errors, timeouts, non-JSON and HTML error pages all fail safely (502, deposit `failed`).
13. Requests are sent as UTF-8 JSON (`ensure_ascii=False`) so the bytes Payme receives are the bytes that were signed.
14. A live-mode callback marked `is_test` in `additional_info` is no longer creditable.
15. A flagged deposit no longer re-queries Payme on every poll and is shown as "under review" in the UI.
16. Database errors raised before the credit transaction (e.g. a locked database) now answer 500 so Payme retries,
    instead of an unhandled exception; a credit for a deleted user is flagged instead of retried for 24 h.
17. UI: added "continue payment" / "refresh status" for unfinished deposits, a delayed-callback state, network-error
    retries, a disabled-service note, and a review state. Success is still shown only for backend `credited`.

Verified in code: signature string = key + non-empty params sorted by name, `|`-joined, excluding `signature` and
`response_signature_string`, null/empty skipped, lowercase hex, constant-time compare; deposit status endpoints are
owner-only (404 otherwise); `CREATE TABLE IF NOT EXISTS` migration leaves existing users, balances and
`wallet_transactions` untouched; the frontend only trusts `GET /wallet/deposits/<id>`; one atomic credit transaction.

## Questions to ask Payme before production activation

1. Is our merchant account enabled for the hosted Checkout (Payment) API (`/api/checkout/url`), not only the JSON-RPC Merchant API?
2. Please confirm in writing that for `currency=UZS` request `amount` and callback `amount`/`actual_amount` are integer tiyin (100020 = 1000 UZS 20 tiyin), and that `actual_amount` equals `amount` for a normal payment.
3. The sample signatures in docs.payme.uz do not reproduce from the strings shown. Please give a verified request and callback example (key, string, SHA1) and confirm how non-string JSON values (numbers, booleans) are stringified.
4. Does the signature include every top-level callback field, including `additional_info` as the raw JSON string, and any fields not in the docs?
5. Is `payment_id` from the callback/status response stable for an order, and can one `order_id` have several payment ids?
6. With `delayed=N`, can an `approved` callback follow `declined` or `expired` for the same order? Exact semantics of `lifetime` expiry versus a payment in progress.
7. Which callbacks are sent for refunds/chargebacks and partial reversals (`order_status`, `reversal_amount`)?
8. Is the callback body always JSON, never form-encoded? Are the source IPs still `54.154.216.60` and `3.75.125.89`? Are callbacks signed in the live environment identically to test?
9. Is the checkout host always `*.payme.uz`? (We refuse other hosts.)
10. Do the contract and merchant category permit wallet top-ups (stored value), holding funds in escrow, and later payouts? What are per-transaction limits and settlement timing?
11. How are test mode and live mode selected (merchant status only, or different base URLs)?
