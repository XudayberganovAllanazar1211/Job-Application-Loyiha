"""Payme sandbox check: proves that the configured merchant credentials and FinJob's signature code are
accepted by the real Payme API. It does NOT touch the FinJob database and never credits anything.

Usage (from backend/, with PAYME_* variables in backend/.env or the environment):
    python payme_sandbox_check.py              # config check + create a test order + signed status check
    python payme_sandbox_check.py --config     # config check only, no network

What it does:
  1. Prints the configuration problems (if any) using the same rules as the app. Secrets are never printed.
  2. Refuses to run against a live merchant: PAYME_TEST_MODE must be 1.
  3. Creates one hosted-checkout order (smallest allowed amount) and prints its checkout URL.
  4. Asks Payme for that order's status and verifies Payme's signature on the answer.
Open the printed checkout URL and pay with a Payme test card to exercise the full flow; the callback then goes to
PAYME_CALLBACK_URL (which must be publicly reachable for that part).
"""
import json
import sys
import uuid

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import payme


def main(argv):
    cfg = payme.load_config()
    summary = payme.config_summary(cfg)
    print("Payme configuration (secrets hidden):")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if cfg["problems"]:
        print("\nNOT READY - fix the problems listed above.")
        return 2
    if not cfg["test_mode"]:
        print("\nRefusing to run: PAYME_TEST_MODE is 0 (live merchant). This check only runs in test mode.")
        return 2
    if "--config" in argv:
        print("\nConfiguration OK.")
        return 0

    order_id = uuid.uuid4().hex
    print(f"\nCreating test order {order_id} for {cfg['min_uzs']} UZS ...")
    try:
        checkout = payme.create_checkout(cfg, order_id, payme.uzs_to_tiyin(cfg["min_uzs"]), timeout=20)
    except payme.PaymeAPIError as exc:
        print(f"FAILED: Payme refused the order ({exc.reason}).")
        if exc.reason == "payme_error_1014":
            print("Payme says the signature is invalid: PAYME_MERCHANT_ID / PAYME_MERCHANT_KEY do not match "
                  "the payment secret key in your Payme merchant cabinet.")
        return 1
    print("OK: Payme accepted the signed order request.")
    print("Checkout URL:", checkout)

    print("\nRequesting signed order status ...")
    try:
        status = payme.fetch_order_status(cfg, order_id, timeout=20)
    except payme.PaymeAPIError as exc:
        print(f"FAILED: status check did not succeed ({exc.reason}).")
        return 1
    print("OK: Payme's status answer carries a valid signature.")
    print("order_status:", status.get("order_status"), "| amount:", status.get("amount"), status.get("currency"))
    theirs = status.get("response_signature_string")
    if theirs:  # test mode only; the secret is masked in it
        ours = payme.payme_signature_string("*", status)
        same = ours.split("|", 1)[-1] == str(theirs).split("|", 1)[-1]
        print("Signature string layout matches Payme's response_signature_string:", same)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
