import { useState } from "react";
import api from "../api";
import { rupeesToPaise } from "../utils";

export default function PayoutForm({ merchant, onSuccess }) {
  const [amount, setAmount] = useState("");
  const [bankId, setBankId] = useState(merchant?.bank_account_id ?? "");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null); // { type: 'success'|'error', msg }

  // Keep bankId in sync when merchant changes
  if (merchant?.bank_account_id && bankId !== merchant.bank_account_id && !loading) {
    setBankId(merchant.bank_account_id);
  }

  const showToast = (type, msg) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 5000);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const paise = rupeesToPaise(amount);
    if (!paise || paise <= 0) {
      showToast("error", "Enter a valid amount greater than ₹0.");
      return;
    }

    setLoading(true);
    try {
      const idempotencyKey = crypto.randomUUID();
      const { data } = await api.post(
        "/payouts/",
        { amount_paise: paise, bank_account_id: bankId },
        { headers: { "Idempotency-Key": idempotencyKey } }
      );
      showToast("success", `Payout created — ID: ${data.id.slice(0, 8).toUpperCase()}…`);
      setAmount("");
      onSuccess?.();
    } catch (err) {
      const errData = err.response?.data;
      if (errData?.error === "insufficient_funds") {
        showToast("error", "Insufficient funds. Top up your ledger balance.");
      } else {
        showToast("error", errData?.error || "Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-2xl bg-white/5 ring-1 ring-white/10 p-6 backdrop-blur-sm shadow-xl">
      <h2 className="mb-5 text-lg font-semibold text-white">Request Payout</h2>

      {/* Toast */}
      {toast && (
        <div className={`mb-4 flex items-start gap-3 rounded-xl px-4 py-3 text-sm font-medium ring-1 ${
          toast.type === "success"
            ? "bg-emerald-500/20 text-emerald-200 ring-emerald-500/30"
            : "bg-red-500/20 text-red-200 ring-red-500/30"
        }`}>
          <span>{toast.type === "success" ? "✅" : "❌"}</span>
          <span>{toast.msg}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block mb-1.5 text-xs font-medium text-slate-400 uppercase tracking-wider">
            Amount (₹)
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 font-semibold">₹</span>
            <input
              id="payout-amount"
              type="number"
              min="0.01"
              step="0.01"
              placeholder="0.00"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
              className="w-full rounded-xl bg-white/10 pl-8 pr-4 py-3 text-white placeholder-slate-500 ring-1 ring-white/10 focus:ring-2 focus:ring-indigo-500 outline-none transition"
            />
          </div>
        </div>

        <div>
          <label className="block mb-1.5 text-xs font-medium text-slate-400 uppercase tracking-wider">
            Bank Account ID
          </label>
          <input
            id="payout-bank-id"
            type="text"
            value={bankId}
            onChange={(e) => setBankId(e.target.value)}
            required
            className="w-full rounded-xl bg-white/10 px-4 py-3 text-white placeholder-slate-500 ring-1 ring-white/10 focus:ring-2 focus:ring-indigo-500 outline-none transition font-mono text-sm"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          id="submit-payout-btn"
          className="w-full rounded-xl bg-gradient-to-r from-indigo-500 to-violet-600 py-3 font-semibold text-white shadow-lg hover:from-indigo-400 hover:to-violet-500 active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
              </svg>
              Processing…
            </span>
          ) : "Send Payout →"}
        </button>
      </form>
    </div>
  );
}
