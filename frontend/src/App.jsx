import { useEffect, useState } from "react";
import api, { setMerchantId } from "./api";
import BalanceCards from "./components/BalanceCards";
import LedgerTable from "./components/LedgerTable";
import PayoutForm from "./components/PayoutForm";
import PayoutTable from "./components/PayoutTable";

export default function App() {
  const [merchants, setMerchants] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [merchant, setMerchant] = useState(null);   // full profile w/ balance
  const [balanceLoading, setBalanceLoading] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0); // bump to trigger table refresh

  // 1 — Fetch merchant list for the switcher (no auth needed)
  useEffect(() => {
    api.get("/merchants/list/").then(({ data }) => {
      setMerchants(data);
      if (data.length > 0) setSelectedId(data[0].id);
    });
  }, []);

  // 2 — When selection changes, update the axios header and fetch profile
  useEffect(() => {
    if (!selectedId) return;
    setMerchantId(selectedId);
    fetchMerchant();
  }, [selectedId]);

  const fetchMerchant = async () => {
    setBalanceLoading(true);
    try {
      const { data } = await api.get("/merchants/me/");
      setMerchant(data);
    } catch { /* ignore */ }
    finally { setBalanceLoading(false); }
  };

  const handlePayoutSuccess = () => {
    fetchMerchant();                        // refresh balance immediately
    setRefreshTick((t) => t + 1);          // tell PayoutTable to refetch now
  };

  const selectedMerchant = merchants.find((m) => m.id === selectedId);

  return (
    <div className="min-h-screen bg-[#0b0f1a] text-white font-sans">
      {/* ── Top Navigation ──────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-50 border-b border-white/10 bg-[#0b0f1a]/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-lg shadow-lg shadow-indigo-500/30">
              💸
            </div>
            <div>
              <h1 className="text-base font-bold leading-tight">Payout Engine</h1>
              <p className="text-[10px] text-slate-500">Merchant Dashboard</p>
            </div>
          </div>

          {/* Merchant Switcher */}
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400">Merchant:</span>
            <select
              id="merchant-switcher"
              value={selectedId ?? ""}
              onChange={(e) => setSelectedId(e.target.value)}
              className="rounded-xl bg-white/10 px-3 py-2 text-sm text-white ring-1 ring-white/10 focus:ring-indigo-500 outline-none cursor-pointer min-w-[180px]"
            >
              {merchants.map((m) => (
                <option key={m.id} value={m.id} className="bg-[#1a2035]">
                  {m.name}
                </option>
              ))}
            </select>

            <button
              onClick={fetchMerchant}
              title="Refresh balance"
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/5 hover:bg-white/10 ring-1 ring-white/10 transition-colors text-sm"
            >
              🔄
            </button>
          </div>
        </div>
      </nav>

      {/* ── Main Content ────────────────────────────────────────────────── */}
      <main className="mx-auto max-w-7xl px-6 py-8 space-y-8">

        {/* Welcome strip */}
        {selectedMerchant && (
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-slate-600 to-slate-800 text-lg ring-2 ring-white/10">
              🏦
            </div>
            <div>
              <p className="text-lg font-semibold">{merchant?.name ?? selectedMerchant.name}</p>
              <p className="text-xs text-slate-400">{merchant?.email ?? "Loading…"}</p>
            </div>
          </div>
        )}

        {/* Section 1 — Balance Cards */}
        <section>
          <BalanceCards balance={merchant?.balance} loading={balanceLoading} />
        </section>

        {/* Section 2 & 3 — Form + Payout Table side by side on large screens */}
        <section className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-1">
            <PayoutForm merchant={merchant} onSuccess={handlePayoutSuccess} />
          </div>
          <div className="lg:col-span-2">
            <PayoutTable refreshTick={refreshTick} />
          </div>
        </section>

        {/* Section 4 — Ledger */}
        <section>
          <LedgerTable key={selectedId} />
        </section>

      </main>

      {/* Footer */}
      <footer className="border-t border-white/5 py-6 text-center text-xs text-slate-600">
        Merchant Payout Engine · Django 4.2 · Celery · React 18 · PostgreSQL
      </footer>
    </div>
  );
}
