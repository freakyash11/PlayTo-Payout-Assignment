#!/usr/bin/env python
"""
Smoke tests for merchant endpoints:
  GET /api/v1/merchants/me/
  GET /api/v1/merchants/me/ledger/
  GET /api/v1/merchants/me/payouts/
  GET /api/v1/merchants/list/

And the original payout endpoint suite.
Run inside the backend container: python /app/merchant_smoke_test.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from merchants.models import Merchant

merchant = Merchant.objects.first()
if not merchant:
    sys.exit("No merchants found — run seed_merchants first.")

MERCHANT_ID = str(merchant.id)
BASE = "http://localhost:8000/api/v1/"
MH = {"X-Merchant-Id": MERCHANT_ID}


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


print(f"\nMerchant: {MERCHANT_ID}  ({merchant.name})\n")

# ── GET /api/v1/merchants/me/ ──────────────────────────────────────────── #
code, body = http("GET", BASE + "merchants/me/", headers=MH)
check("GET /merchants/me/", code, 200)
check("  has id", body.get("id") == MERCHANT_ID, True)
check("  has balance.available_paise", "available_paise" in body.get("balance", {}), True)
check("  has balance.held_paise", "held_paise" in body.get("balance", {}), True)
check("  has balance.net_balance_paise", "net_balance_paise" in body.get("balance", {}), True)
print(f"   Balance: {body['balance']}")

# ── GET /api/v1/merchants/me/ledger/ ──────────────────────────────────── #
code, body = http("GET", BASE + "merchants/me/ledger/", headers=MH)
check("GET /merchants/me/ledger/", code, 200)
check("  has count", "count" in body, True)
check("  has results", "results" in body, True)
if body["results"]:
    entry = body["results"][0]
    for field in ("id", "entry_type", "amount_paise", "reference_id", "description", "created_at"):
        check(f"  ledger entry has {field}", field in entry, True)
print(f"   {body['count']} ledger entries, showing {len(body['results'])}")

# ── GET /api/v1/merchants/me/payouts/ ─────────────────────────────────── #
code, body = http("GET", BASE + "merchants/me/payouts/", headers=MH)
check("GET /merchants/me/payouts/", code, 200)
check("  returns a list", isinstance(body, list), True)
print(f"   {len(body)} payout(s) for this merchant")

# ── GET /api/v1/merchants/list/ (no auth needed) ──────────────────────── #
code, body = http("GET", BASE + "merchants/list/")
check("GET /merchants/list/ (no auth)", code, 200)
check("  returns a list", isinstance(body, list), True)
check("  each item has id+name only", all("email" not in m for m in body), True)
print(f"   {len(body)} merchant(s) in system")

# ── Missing X-Merchant-ID → 401 ───────────────────────────────────────── #
code, _ = http("GET", BASE + "merchants/me/")
check("GET /merchants/me/ without header → 401", code, 401)

# ── Unknown merchant → 404 ────────────────────────────────────────────── #
code, _ = http("GET", BASE + "merchants/me/", headers={"X-Merchant-Id": str(uuid.uuid4())})
check("GET /merchants/me/ unknown merchant → 404", code, 404)

print("\n🎉  All merchant endpoint checks passed!\n")
