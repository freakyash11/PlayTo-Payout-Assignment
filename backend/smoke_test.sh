#!/bin/sh
set -e

MERCHANT_ID=$(python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from merchants.models import Merchant
print(Merchant.objects.first().id)
")

IDEM_KEY=$(python -c "import uuid; print(uuid.uuid4())")
IDEM_KEY2=$(python -c "import uuid; print(uuid.uuid4())")
IDEM_KEY3=$(python -c "import uuid; print(uuid.uuid4())")

BASE="http://localhost:8000/api/v1/payouts/"
CT='-H Content-Type:application/json'
MH="-H X-Merchant-Id:$MERCHANT_ID"
IH="-H Idempotency-Key:$IDEM_KEY"

echo "Merchant: $MERCHANT_ID"
echo "Idempotency key: $IDEM_KEY"

echo ""
echo "=== POST #1 (new payout, expect 201) ==="
curl -sf -w "\nHTTP %{http_code}\n" -X POST "$BASE" \
  -H "Content-Type: application/json" \
  -H "X-Merchant-Id: $MERCHANT_ID" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -d '{"amount_paise": 50000, "bank_account_id": "HDFC00012345678"}' \
  | python -m json.tool 2>/dev/null || true

echo ""
echo "=== POST #2 (duplicate key, expect 200) ==="
curl -sf -w "\nHTTP %{http_code}\n" -X POST "$BASE" \
  -H "Content-Type: application/json" \
  -H "X-Merchant-Id: $MERCHANT_ID" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -d '{"amount_paise": 50000, "bank_account_id": "HDFC00012345678"}' \
  | python -m json.tool 2>/dev/null || true

echo ""
echo "=== GET list (expect 200) ==="
curl -sf -o /dev/null -w "HTTP %{http_code}\n" "$BASE" \
  -H "X-Merchant-Id: $MERCHANT_ID"

echo ""
echo "=== POST — insufficient funds (expect 402) ==="
curl -s -w "\nHTTP %{http_code}\n" -X POST "$BASE" \
  -H "Content-Type: application/json" \
  -H "X-Merchant-Id: $MERCHANT_ID" \
  -H "Idempotency-Key: $IDEM_KEY2" \
  -d '{"amount_paise": 999999999, "bank_account_id": "X"}'
echo

echo ""
echo "=== POST — missing X-Merchant-ID (expect 401) ==="
curl -s -w "\nHTTP %{http_code}\n" -X POST "$BASE" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDEM_KEY3" \
  -d '{"amount_paise": 50000, "bank_account_id": "X"}'
echo

echo ""
echo "=== POST — missing Idempotency-Key (expect 400) ==="
curl -s -w "\nHTTP %{http_code}\n" -X POST "$BASE" \
  -H "Content-Type: application/json" \
  -H "X-Merchant-Id: $MERCHANT_ID" \
  -d '{"amount_paise": 50000, "bank_account_id": "X"}'
echo
