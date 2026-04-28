# Playto Payout Engine: Technical Deep Dive

This document explains five critical systems that work together to safely handle concurrent merchant payout requests without race conditions, overdrafts, or data loss.

---

## 1. The Ledger

### The Complete `get_balance_breakdown()` Method

```python
def get_balance_breakdown(self):
    """Returns dict with available_balance and held_balance using DB aggregation.

    NOTE: Importing Payout here (inside the method) avoids a circular import
    since payouts.models imports nothing from merchants.models at module level.
    """
    from django.db.models import Q  # noqa: F401 – kept for future filters
    from payouts.models import Payout

    total_credits = (
        self.ledger_entries.filter(entry_type="CREDIT")
        .aggregate(total=Sum("amount_paise"))["total"]
        or 0
    )

    total_debits = (
        self.ledger_entries.filter(entry_type="DEBIT")
        .aggregate(total=Sum("amount_paise"))["total"]
        or 0
    )

    held = (
        Payout.objects.filter(
            merchant=self,
            status__in=["pending", "processing"],
        )
        .aggregate(total=Sum("amount_paise"))["total"]
        or 0
    )

    net_balance = total_credits - total_debits
    available = net_balance - held

    return {
        "net_balance_paise": net_balance,
        "held_paise": held,
        "available_paise": available,
    }
```

### Why Separate LedgerEntry Rows Instead of a Mutable Balance Column?

A mutable balance column on the `Merchant` table would create a **compare-and-swap** problem:
- Transaction A reads balance = 10,000 paise
- Transaction B reads balance = 10,000 paise (no lock exists yet)
- Transaction A deducts 5,000 → writes balance = 5,000 ✓ commits
- Transaction B deducts 6,000 → writes balance = 4,000 ✗ commits (but should have failed!)

By using immutable, append-only `LedgerEntry` rows, every financial event is a permanent record. The balance is **derived at query time** via aggregation, which is naturally atomic in SQL:

```sql
SELECT 
    (SELECT COALESCE(SUM(amount_paise), 0) FROM ledger_entries WHERE merchant_id = ? AND entry_type = 'CREDIT')
    -
    (SELECT COALESCE(SUM(amount_paise), 0) FROM ledger_entries WHERE merchant_id = ? AND entry_type = 'DEBIT')
AS net_balance
```

There is no "stale read" problem because the aggregation always queries the latest committed rows.

### Why BigIntegerField Instead of DecimalField or FloatField?

- **FloatField**: Binary floating-point cannot exactly represent decimal amounts. 0.1 + 0.2 ≠ 0.3 in IEEE 754. Financial data loses precision.
- **DecimalField**: Works correctly but is stored as a text string in PostgreSQL (NUMERIC type). Aggregation via SUM() works, but it's slower and uses more storage.
- **BigIntegerField**: Money is stored in **paise** (smallest unit: 1 paise = 1/100 rupee). Integer arithmetic is exact, fast, and requires no string conversion.

Example:
- ₹123.45 = 12,345 paise (BigIntegerField)
- SUM(amount_paise) WHERE merchant_id = X is pure integer arithmetic, no rounding errors.

### What "Balance Derived from DB Aggregation" Means and Why Python sum() is Wrong

**DB aggregation** means:
```sql
SELECT SUM(amount_paise) FROM ledger_entries WHERE merchant_id = ? AND entry_type = 'CREDIT'
```

This is computed **inside the database**, atomically, as a single SQL query. The database engine optimizes it, applies indexes, and returns one number.

**Python sum() on fetched rows** would be:
```python
entries = LedgerEntry.objects.filter(merchant=merchant, entry_type="CREDIT")
total = sum(e.amount_paise for e in entries)
```

Why this is wrong:
1. **Race condition**: Between fetching rows and computing sum(), new rows can be inserted. The sum is stale.
2. **Unbounded memory**: Fetching 1 million rows into Python consumes gigabytes of RAM.
3. **No atomicity guarantee**: If the connection dies mid-iteration, the sum is partial and incorrect.
4. **No isolation**: A concurrent transaction may be mid-INSERT while you sum, giving you a torn view.

The database query is **atomically consistent**: it reads all matching rows at a single point in time (the query start), computes in SQL, and returns one answer.

---

## 2. The Lock

### The Exact `select_for_update()` Block from `views.py`

```python
# a) Row-level lock on the merchant.
#    SELECT FOR UPDATE blocks any concurrent transaction that tries
#    to lock the same merchant row — this is the ONLY correct way
#    to prevent the double-spend race condition in PostgreSQL.
#    Python-level locks (threading.Lock, etc.) are NOT sufficient
#    because they don't span database connections / worker processes.
merchant = Merchant.objects.select_for_update().get(id=merchant.id)

# b) Derive available balance using DB aggregation — inside the lock
#    so that no committed write can slip in between the check and the
#    subsequent INSERT.
breakdown = merchant.get_balance_breakdown()
available_paise = breakdown["available_paise"]
```

### What SQL It Emits

```sql
SELECT * FROM merchants WHERE id = 'abc-123' FOR UPDATE;
```

PostgreSQL acquires an **exclusive row-level lock** on the matching row. Until this transaction commits or rolls back, no other transaction can acquire a lock on the same row.

### What Happens When Two Transactions Hit `select_for_update()` Simultaneously?

**Timeline:**

| Time | Txn A | Txn B |
|------|-------|-------|
| T1   | Sends `SELECT ... FOR UPDATE` on merchant X | — |
| T2   | **Acquires lock**, lock status = 'A' | — |
| T3   | — | Sends `SELECT ... FOR UPDATE` on merchant X |
| T4   | — | **Blocks, waiting for lock** (calls into OS scheduler, sleeps) |
| T5   | Checks balance, creates payout, inserts ledger entry | — |
| T6   | **COMMIT** (lock released) | — |
| T7   | — | **Wakes up, acquires lock**, re-reads merchant row |
| T8   | — | Checks balance (now reflects Txn A's changes), creates payout |
| T9   | — | **COMMIT** (lock released) |

**The key point**: Txn B is **blocked at the database level** (not in Python). The OS suspends Txn B's worker thread/process until the lock becomes available. This is true serialization.

### Why a Python `threading.Lock()` is Wrong for This Use Case

```python
import threading
lock = threading.Lock()

def bad_payment_flow():
    with lock:
        # Check balance
        balance = merchant.balance
        if balance < payout_amount:
            return
        # Create payout
        ...
```

Problems:

1. **Only works within a single Python process**: If you have multiple Gunicorn workers (4–32 processes), each has its own lock object. Two workers can both enter the critical section simultaneously.
2. **Does not span database connections**: Even if you use a Python thread lock, a second database connection (from another worker, container, or service) is never checked by your lock.
3. **Violates isolation**: Another application or a Celery task can query the database and see uncommitted state between the `balance` read and the `INSERT payout` write.
4. **No persistence across restarts**: A server restart clears all locks; in-flight transactions can reorder.

The database lock (`SELECT FOR UPDATE`) is enforced by the **PostgreSQL server itself**, not by Python, and is effective across:
- Multiple threads in one process
- Multiple processes in one machine
- Multiple machines (all connecting to the same PostgreSQL server)

### The Exact Race Condition Interleaving WITHOUT the Lock

**The Overdraft Scenario:**

Starting state:
- Merchant balance: 1,000 paise (10 rupees)
- Payout A: 600 paise
- Payout B: 600 paise

Without `select_for_update()`, interleaving occurs:

```
Time | Worker A | Worker B | DB State (balance held / available)
-----|----------|---------|------------------------------------
T1   | GET merchant.id | — | (available = 1000)
T2   | — | GET merchant.id | (available = 1000)
T3   | SELECT SUM(CREDITS) - SUM(DEBITS) = 1000 | — | 
T4   | available = 1000, check: 1000 >= 600 ✓ | — |
T5   | — | SELECT SUM(CREDITS) - SUM(DEBITS) = 1000 |
T6   | — | available = 1000, check: 1000 >= 600 ✓ |
T7   | INSERT Payout A (600), INSERT DEBIT (600) | — | (committed!)
T8   | COMMIT, available = 1000 - 600 = 400 | — |
T9   | — | INSERT Payout B (600), INSERT DEBIT (600) | **OVERDRAFT!**
T10  | — | COMMIT | **available = 400 - 600 = -200 (NEGATIVE!)**
```

Both checks pass at T4 and T6 because neither worker has locked the merchant row. By T10, the merchant is overdrawn by 200 paise.

**With `select_for_update()`:**

```
Time | Worker A | Worker B | DB State
-----|----------|---------|------------------------------------
T1   | SELECT ... FOR UPDATE merchant.id | — | (A acquires lock)
T2   | — | SELECT ... FOR UPDATE merchant.id | (B **blocks**)
T3   | available = 1000, check: 1000 >= 600 ✓ | (still blocked) |
T4   | INSERT Payout A, INSERT DEBIT | (still blocked) |
T5   | COMMIT (lock released) | (still pending) |
T6   | — | **Acquires lock**, re-reads: available = 400 |
T7   | — | check: 400 >= 600 **✗ REJECTED** | 402 Payment Required
```

Worker B is forced to wait, and when it acquires the lock, the balance is already updated by Worker A.

---

## 3. The Idempotency

### IdempotencyRecord Lookup Code (Verbatim, Including TTL Filter)

```python
# ── Step 1: Idempotency check — BEFORE acquiring any lock ─────── #
# Only replay responses within the TTL window.  A key older than
# IDEMPOTENCY_KEY_TTL_HOURS is treated as expired: the caller gets a
# fresh payout, which prevents stale 'pending' snapshots being
# replayed long after the payout completed or failed.
ttl_cutoff = timezone.now() - timedelta(hours=self.IDEMPOTENCY_KEY_TTL_HOURS)
try:
    record = IdempotencyRecord.objects.get(
        merchant=merchant,
        idempotency_key=idempotency_key,
        created_at__gte=ttl_cutoff,
    )
    # Return the exact same response that was sent originally.
    return Response(record.response_body, status=status.HTTP_200_OK)
except IdempotencyRecord.DoesNotExist:
    pass
```

### Where the Check Happens Relative to the Lock (Before, and Why)

The check happens **BEFORE entering the atomic transaction** (which acquires the lock).

**Why before?**

1. **Avoid unnecessary lock contention**: If an idempotent duplicate arrives, we can return the cached response immediately without waiting for a lock. This reduces lock hold time.
2. **Performance**: A fast lookup in the `idempotency_records` table (indexed on `(merchant, idempotency_key)`) is much faster than acquiring a row lock on the merchant.
3. **Safety**: Even if Step 1 misses (no record found, but one is being created by a concurrent request), the IntegrityError handler in Step 2 will catch it and replay the now-committed record.

Sequence:
```
Step 1: Idempotency check (no lock)
  ↓
  [if found, return cached response ✓]
  [if not found, proceed ↓]
  ↓
Step 2: Atomic transaction (acquires lock)
  a) SELECT FOR UPDATE merchant
  b) Check balance
  c) Create payout
  d) Create ledger entry
  e) Create idempotency record
  [if IntegrityError, retry lookup ✓]
```

### What Happens When Two Requests with the Same Key Arrive Simultaneously?

Both requests pass Step 1 (no IdempotencyRecord exists yet) and reach Step 2 simultaneously.

**Timeline:**

```
Time | Request A | Request B | DB State
-----|-----------|-----------|----------------------------------
T1   | Step 1: Lookup idempotency key → not found | — | No record
T2   | — | Step 1: Lookup idempotency key → not found | No record
T3   | Step 2: BEGIN TRANSACTION | — |
T4   | — | Step 2: BEGIN TRANSACTION |
T5   | SELECT FOR UPDATE merchant | — | A locks merchant row
T6   | — | SELECT FOR UPDATE merchant | B **blocks** waiting for lock
T7   | Check balance (1000 >= 600 ✓) | (blocked) |
T8   | INSERT Payout (600) | (blocked) |
T9   | INSERT DEBIT LedgerEntry | (blocked) |
T10  | INSERT IdempotencyRecord ✓ | (blocked) |
T11  | COMMIT (release lock) | (still blocked) |
T12  | — | **Lock acquired, re-read merchant** | balance now 400
T13  | — | Check balance (400 >= 600 ✗) | return 402 Payment Required
T14  | — | — | B's transaction rolled back, idempotency record from A exists
```

But there is a **second scenario** where a race happens inside the lock:

**Request A and Request B both create Payout + IdempotencyRecord:**

```
T1-T10  [Both A and B execute steps in parallel somehow...]
T11     A's INSERT IdempotencyRecord succeeds
T12     B's INSERT IdempotencyRecord fails with IntegrityError (unique_together)
        → B's entire transaction is rolled back by PostgreSQL
T13     [B's IntegrityError handler catches this]
```

### The IntegrityError Except Block (Verbatim)

```python
except IntegrityError:
    # A concurrent request with the same idempotency key committed
    # just before us and already created the Payout + IdempotencyRecord.
    # The transaction above was rolled back automatically by PostgreSQL.
    # Re-fetch the now-committed record and replay the original response.
    try:
        record = IdempotencyRecord.objects.get(
            merchant=merchant,
            idempotency_key=idempotency_key,
            created_at__gte=ttl_cutoff,
        )
        return Response(record.response_body, status=status.HTTP_200_OK)
    except IdempotencyRecord.DoesNotExist:
        # Should be unreachable: IntegrityError must have come from
        # IdempotencyRecord or Payout unique constraint, so the record
        # must exist.  Return 409 as a last resort.
        return Response(
            {"error": "Concurrent request conflict. Please retry."},
            status=status.HTTP_409_CONFLICT,
        )
```

### How Storing `response_body` as a JSONField Solves the "Same Response" Requirement

An IdempotencyRecord stores the **exact JSON response** sent to the client:

```python
response_data = PayoutSerializer(payout).data
IdempotencyRecord.objects.create(
    merchant=merchant,
    idempotency_key=idempotency_key,
    response_body=dict(response_data),  # ← JSONField stores this
)
```

When a duplicate request arrives, the view returns:

```python
return Response(record.response_body, status=status.HTTP_200_OK)
```

This is **byte-for-byte identical** to what the first request received (same payout ID, same amount, same status, same timestamps). The client cannot tell it's a replay.

Without storing the response, the server would have to re-fetch the Payout and re-serialize it. But if the Payout was since updated (status changed to 'completed', for example), the replayed response would differ, breaking the idempotency guarantee.

### How the 24-Hour Expiry is Enforced

The TTL is enforced **at lookup time**, not by deleting records:

```python
ttl_cutoff = timezone.now() - timedelta(hours=self.IDEMPOTENCY_KEY_TTL_HOURS)
record = IdempotencyRecord.objects.get(
    merchant=merchant,
    idempotency_key=idempotency_key,
    created_at__gte=ttl_cutoff,  # ← Filters out old records
)
```

If a duplicate request arrives 25 hours later with the same key, the lookup fails (no record found within the TTL window), and a **fresh payout** is created. This prevents stale pending snapshots from being replayed indefinitely.

**Benefits of this approach:**
- No background cleanup jobs; no cron overhead.
- Records remain in the database for auditing/debugging.
- TTL can be changed in code without data migration.

### Confirm Keys are Scoped Per Merchant

The unique constraint proves scoping:

```python
class IdempotencyRecord(models.Model):
    ...
    class Meta:
        unique_together = [("merchant", "idempotency_key")]
```

Two different merchants can use the **same idempotency key** without collision:
- Merchant A, key "uuid-123" → stored in row X
- Merchant B, key "uuid-123" → stored in row Y (different row, no conflict)

The lookup also filters by merchant:

```python
record = IdempotencyRecord.objects.get(
    merchant=merchant,  # ← Scoped to this merchant
    idempotency_key=idempotency_key,
    created_at__gte=ttl_cutoff,
)
```

---

## 4. The State Machine

### ALLOWED_TRANSITIONS Dict (Verbatim)

```python
# Explicit allowlist of legal status transitions.
# Any pair not present here is forbidden.
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    PENDING: [PROCESSING],
    PROCESSING: [COMPLETED, FAILED],
    COMPLETED: [],
    FAILED: [],
}
```

### `transition_to()` Method (Verbatim)

```python
def transition_to(self, new_status: str) -> None:
    """Validate and apply a status transition **in memory only**.

    The caller is responsible for persisting the change inside a
    database transaction. This method intentionally does NOT call
    self.save() so that the caller controls atomicity.

    Raises:
        ValueError: If the transition is not in ALLOWED_TRANSITIONS.
    """
    allowed = self.ALLOWED_TRANSITIONS.get(self.status, [])
    if new_status not in allowed:
        raise ValueError(
            f"Illegal transition: {self.status} -> {new_status}"
        )
    self.status = new_status
```

### Exactly Where Failed→Completed is Blocked

The dict entry for FAILED is:

```python
FAILED: [],  # ← Empty list: no transitions allowed FROM failed
```

When the code attempts:
```python
payout.transition_to(Payout.COMPLETED)  # while status == 'failed'
```

The `transition_to()` method executes:

```python
allowed = self.ALLOWED_TRANSITIONS.get(self.status, [])  # allowed = []
if new_status not in allowed:  # 'completed' not in []? TRUE
    raise ValueError(
        f"Illegal transition: {self.status} -> {new_status}"
        # Raises: "Illegal transition: failed -> completed"
    )
```

### Why `transition_to()` Does Not Call `self.save()`

By not calling `save()`, the method ensures that **the caller controls atomicity**. This allows:

```python
with transaction.atomic():
    payout.transition_to(Payout.COMPLETED)
    # Other operations (e.g., create ledger entries)
    payout.save()  # ← Caller saves, inside the transaction
    # If any operation fails, entire transaction rolls back
```

If `transition_to()` called `save()` internally:

```python
def transition_to(self, new_status: str) -> None:
    allowed = self.ALLOWED_TRANSITIONS.get(self.status, [])
    if new_status not in allowed:
        raise ValueError(...)
    self.status = new_status
    self.save()  # ← Saves immediately, might commit before other work
```

Then a sequence like this becomes unsafe:

```python
with transaction.atomic():
    payout.transition_to(Payout.COMPLETED)  # ← saves, commits status
    LedgerEntry.objects.create(...)  # ← if this fails, status already committed!
```

The status update is durable but the ledger entry is rolled back, leaving the payout in an inconsistent state.

### The Failure Path from `tasks.py` (Status Transition + Fund Return in Same Block)

```python
elif outcome == "failure":
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)
        payout.transition_to(Payout.FAILED)
        payout.failure_reason = "Bank declined"
        payout.save()
        # ATOMICALLY return the held funds to the merchant's ledger.
        # If this INSERT fails the status update above is also rolled back.
        LedgerEntry.objects.create(
            merchant=payout.merchant,
            entry_type="CREDIT",
            amount_paise=payout.amount_paise,
            reference_id=str(payout.id),
            description="Payout reversal: bank declined",
        )
```

Both operations (status → FAILED and credit reversal) are inside the same `with transaction.atomic():` block. If the `LedgerEntry.objects.create()` raises any exception, PostgreSQL rolls back the entire transaction, including the `payout.save()`.

### What Would Happen WITHOUT the Atomic Block (Crash Scenario)

```python
# WRONG: Not atomic
elif outcome == "failure":
    payout.transition_to(Payout.FAILED)
    payout.failure_reason = "Bank declined"
    payout.save()  # ← Commits to DB, transaction complete (if autocommit=True)
    
    # Now crash before this line:
    LedgerEntry.objects.create(
        merchant=payout.merchant,
        entry_type="CREDIT",
        amount_paise=payout.amount_paise,
        reference_id=str(payout.id),
        description="Payout reversal: bank declined",
    )
```

Timeline:

```
Time | Event
-----|---------------------------------------------------
T1   | payout.status = 'failed'
T2   | payout.save() — **writes to DB, transaction commits**
T3   | Worker crashes / network cut / exception raised
T4   | Ledger entry is NEVER created
T5   | Merchant's balance still reflects the original DEBIT
T6   | Payout status is FAILED but funds are never returned
T7   | Merchant has **lost money** (held funds never released)
```

The merchant requested a payout, the bank declined, the status is marked FAILED, but the funds are not returned. This is a **financial loss bug**.

With the atomic block, if the worker crashes at T3, PostgreSQL will see the connection drop, automatically rollback the transaction, and the payout status reverts to PROCESSING. A retry mechanism (or manual intervention) can then attempt the failure path again, ensuring both status and credit reversal happen together or not at all.

---

## 5. The AI Audit

### What the AI Wrote

In an earlier version of `retry_stuck_payouts()`, the permanent failure path had this structure:

```python
if payout.attempts >= 3:
    payout.transition_to(Payout.FAILED)
    payout.failure_reason = "Max retries exceeded"
    payout.save()
    LedgerEntry.objects.create(
        merchant=payout.merchant,
        entry_type="CREDIT",
        amount_paise=payout.amount_paise,
        reference_id=str(payout.id),
        description="Payout reversal: max retries exceeded",
    )
```

This code was **not wrapped in `transaction.atomic()`**.

### What Was Wrong

The failure mode is identical to the scenario described in Section 4:

1. `payout.save()` completes and the database transaction commits (because we were already inside `transaction.atomic()` from the outer loop, but the logic here suggests it wasn't).
2. If `LedgerEntry.objects.create()` raises an exception (e.g., database connection failure, out of memory, or a database constraint violation), the exception propagates.
3. The payout status is already **durably persisted as FAILED**, but the **credit reversal is never created**.
4. The merchant loses the payout amount permanently.

**Exact interleaving that causes data loss:**

```
Time | Event | Payout Status | Ledger (CREDIT entries)
-----|-------|---------------|------------------------
T1   | Read payout from DB | PROCESSING | (DEBIT for 600 paise)
T2   | Check: attempts (3) >= 3? YES | PROCESSING | (DEBIT for 600)
T3   | Call payout.save() | FAILED | (DEBIT for 600)
T4   | **Database commits** | **FAILED (durable)** | (DEBIT for 600)
T5   | Call LedgerEntry.objects.create() — exception! | FAILED | (DEBIT for 600)
T6   | Exception propagates, Celery task fails | FAILED | (DEBIT for 600)
T7   | Worker restarts, retries task | FAILED | (DEBIT for 600)
T8   | Payout status is FAILED, so retry_stuck_payouts skips it | FAILED | (DEBIT for 600)
T∞   | **Funds are never returned to merchant** | FAILED | (DEBIT for 600)
```

The balance breakdown would show:
```python
available_paise = net_balance - held
             = (credits - debits) - held_in_payouts
             = (0 - 600) - 0  # ← 600 paise never credited back!
             = -600  # ← NEGATIVE
```

The merchant's balance would be negative/stuck.

### What I Replaced It With

The fix: wrap both operations in the same atomic block:

```python
if payout.attempts >= 3:
    with transaction.atomic():
        payout.transition_to(Payout.FAILED)
        payout.failure_reason = "Max retries exceeded"
        payout.save()
        LedgerEntry.objects.create(
            merchant=payout.merchant,
            entry_type="CREDIT",
            amount_paise=payout.amount_paise,
            reference_id=str(payout.id),
            description="Payout reversal: max retries exceeded",
        )
```

Now, if `LedgerEntry.objects.create()` raises an exception:

```
Time | Event | Payout Status | Ledger (CREDIT entries)
-----|-------|---------------|------------------------
T1   | Read payout from DB | PROCESSING | (DEBIT for 600)
T2   | Check: attempts (3) >= 3? YES | PROCESSING | (DEBIT for 600)
T3   | with transaction.atomic(): | PROCESSING | (DEBIT for 600)
T4   | Call payout.save() | FAILED (in-memory) | (DEBIT for 600)
T5   | Call LedgerEntry.objects.create() — exception! | FAILED (in-memory) | (DEBIT for 600)
T6   | **PostgreSQL rolls back entire transaction** | PROCESSING (rolled back!) | (DEBIT for 600, no new CREDIT)
T7   | Exception propagates, Celery task fails | PROCESSING | (DEBIT for 600)
T8   | retry_stuck_payouts runs again 30 seconds later | PROCESSING | (DEBIT for 600)
T9   | Retries the same block (status + credit entry) | FAILED ✓ | (DEBIT for 600, **CREDIT for 600**)
T10  | **Both operations succeed**, transaction commits | FAILED | (DEBIT -600, CREDIT +600 = 0)
T∞   | Balance is correct, payout is marked FAILED | FAILED | available_paise = 0 (neutral)
```

**Result**: Both the status transition and the credit reversal **happen together or not at all**. If a crash occurs, the retry mechanism will eventually restore consistency.

---

## Summary

These five systems work in concert:

1. **The Ledger** (append-only entries, DB aggregation): Prevents balance corruption via immutability and atomic queries.
2. **The Lock** (`SELECT FOR UPDATE`): Serializes concurrent balance checks and payout creation, preventing overdrafts.
3. **The Idempotency** (KeyRecord + TTL): Ensures duplicate requests get the same response without replaying side effects.
4. **The State Machine** (ALLOWED_TRANSITIONS + no-save pattern): Enforces legal status flows and lets the caller control atomicity.
5. **Atomicity** (transaction.atomic() wrapping all related writes): Ensures that status changes and fund reversals are all-or-nothing, preventing data loss on failure.

Together, they guarantee:
- ✅ No race conditions (locks)
- ✅ No overdrafts (balance check inside lock)
- ✅ No duplicate charges (idempotency)
- ✅ No invalid state transitions (state machine)
- ✅ No lost funds (atomic status + ledger updates)
