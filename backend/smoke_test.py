#!/usr/bin/env python
"""
Smoke test for POST/GET /api/v1/payouts/
Run inside the backend container: python /app/smoke_test.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

# ── Bootstrap Django to get a real merchant ID ────────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from merchants.models import Merchant  # noqa: E402

merchant = Merchant.objects.first()
if not merchant:
    sys.exit("No merchants found – run seed_merchants first.")

MERCHANT_ID = str(merchant.id)
BASE = "http://localhost:8000/api/v1/payouts/"

# ── Helpers ───────────────────────────────────────────────────────────────

def http(method, url, *, headers=None, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def check(label, got, want):
    icon = "✅" if got == want else "❌"
    print(f"{icon}  {label}: {got}  (expected {want})")
    if got != want:
        sys.exit(1)

# ── Tests ─────────────────────────────────────────────────────────────────
print(f"\nMerchant: {MERCHANT_ID}\n")

idem1 = str(uuid.uuid4())
hdrs_post = {
    "Content-Type": "application/json",
    "X-Merchant-Id": MERCHANT_ID,
    "Idempotency-Key": idem1,
}

# 1. New payout → 201
code, body = http("POST", BASE, headers=hdrs_post, body={"amount_paise": 50000, "bank_account_id": "HDFC001"})
check("POST new payout", code, 201)
payout_id = body["id"]
print(f"   Payout ID: {payout_id}")
print(f"   Merchant:  {body['merchant_id']}")
print(f"   Status:    {body['status']}")

# 2. Duplicate key → 200 with same payout ID
code2, body2 = http("POST", BASE, headers=hdrs_post, body={"amount_paise": 50000, "bank_account_id": "HDFC001"})
check("POST duplicate key (idempotency replay)", code2, 200)
check("  IDs match", body2["id"] == payout_id, True)

# 3. GET list → 200
code3, _ = http("GET", BASE, headers={"X-Merchant-Id": MERCHANT_ID})
check("GET list", code3, 200)

# 4. GET single → 200
code4, body4 = http("GET", BASE + payout_id + "/", headers={"X-Merchant-Id": MERCHANT_ID})
check("GET single", code4, 200)
check("  Correct payout returned", body4["id"] == payout_id, True)

# 5. Insufficient funds → 402
code5, body5 = http(
    "POST", BASE,
    headers={**hdrs_post, "Idempotency-Key": str(uuid.uuid4())},
    body={"amount_paise": 999_999_999, "bank_account_id": "X"},
)
check("POST insufficient funds", code5, 402)
check("  error field", body5.get("error"), "insufficient_funds")

# 6. Missing X-Merchant-ID → 401
code6, _ = http("POST", BASE, headers={"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())}, body={"amount_paise": 100, "bank_account_id": "X"})
check("POST missing X-Merchant-ID", code6, 401)

# 7. Missing Idempotency-Key → 400
code7, _ = http("POST", BASE, headers={"Content-Type": "application/json", "X-Merchant-Id": MERCHANT_ID}, body={"amount_paise": 100, "bank_account_id": "X"})
check("POST missing Idempotency-Key", code7, 400)

# 8. Invalid UUID Idempotency-Key → 400
code8, _ = http("POST", BASE, headers={"Content-Type": "application/json", "X-Merchant-Id": MERCHANT_ID, "Idempotency-Key": "not-a-uuid"}, body={"amount_paise": 100, "bank_account_id": "X"})
check("POST invalid Idempotency-Key UUID", code8, 400)

print("\n🎉  All checks passed!\n")
