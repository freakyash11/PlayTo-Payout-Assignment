import { useEffect, useRef, useState } from "react";
import api from "../api";
import { fmtDate, formatRupees, shortId } from "../utils";

const STATUS_STYLES = {
  pending:    "bg-slate-500/20 text-slate-300 ring-slate-500/30",
  processing: "bg-blue-500/20 text-blue-300 ring-blue-500/30 animate-pulse",
  completed:  "bg-emerald-500/20 text-emerald-300 ring-emerald-500/30",
  failed:     "bg-red-500/20 text-red-300 ring-red-500/30",
};

const STATUS_ICONS = {
  pending: "○",
  processing: "◉",
  completed: "✓",
  failed: "✕",
};

function SkeletonRow() {
  return (
    <tr>
      {[...Array(5)].map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 rounded bg-white/10 animate-pulse" style={{ width: `${60 + i * 10}%` }} />
        </td>
      ))}
    </tr>
  );
}

export default function PayoutTable({ refreshTick }) {
  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef(null);

  const fetchPayouts = async () => {
    try {
      const { data } = await api.get("/payouts/");
      setPayouts(data);
    } catch {
      // silently ignore polling errors
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPayouts();
    intervalRef.current = setInterval(fetchPayouts, 5000);
    return () => clearInterval(intervalRef.current);
  }, []);

  // Also refetch immediately when parent signals a new payout was created
  useEffect(() => {
    if (refreshTick > 0) fetchPayouts();
  }, [refreshTick]);

  return (
    <div className="rounded-2xl bg-white/5 ring-1 ring-white/10 backdrop-blur-sm shadow-xl overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
        <h2 className="text-lg font-semibold text-white">Payout History</h2>
        <span className="text-xs text-slate-400 flex items-center gap-1.5">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          Live · 5s refresh
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10">
              {["ID", "Amount", "Status", "Bank Account", "Created At"].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {loading ? (
              [...Array(4)].map((_, i) => <SkeletonRow key={i} />)
            ) : payouts.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-slate-500 text-sm">
                  No payouts yet. Submit one above ↑
                </td>
              </tr>
            ) : (
              payouts.map((p) => (
                <tr key={p.id} className="hover:bg-white/5 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-slate-300">{shortId(p.id)}…</td>
                  <td className="px-4 py-3 font-semibold text-white">{formatRupees(p.amount_paise)}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${STATUS_STYLES[p.status] ?? STATUS_STYLES.pending}`}>
                      <span>{STATUS_ICONS[p.status] ?? "○"}</span>
                      {p.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">{p.bank_account_id}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{fmtDate(p.created_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
