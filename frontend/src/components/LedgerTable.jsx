import { useEffect, useState } from "react";
import api from "../api";
import { fmtDate, formatRupees } from "../utils";

export default function LedgerTable() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/merchants/me/ledger/")
      .then(({ data }) => setEntries(data.results ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="rounded-2xl bg-white/5 ring-1 ring-white/10 backdrop-blur-sm shadow-xl overflow-hidden">
      <div className="px-6 py-4 border-b border-white/10">
        <h2 className="text-lg font-semibold text-white">Recent Ledger Entries</h2>
        <p className="text-xs text-slate-400 mt-0.5">Last 20 entries · credits in green · debits in red</p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10">
              {["Type", "Amount", "Description", "Reference", "Date"].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {loading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i}>
                  {[...Array(5)].map((__, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 rounded bg-white/10 animate-pulse" />
                    </td>
                  ))}
                </tr>
              ))
            ) : entries.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-slate-500 text-sm">
                  No ledger entries found.
                </td>
              </tr>
            ) : (
              entries.map((e) => {
                const isCredit = e.entry_type === "CREDIT";
                return (
                  <tr key={e.id} className="hover:bg-white/5 transition-colors">
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ${
                        isCredit
                          ? "bg-emerald-500/20 text-emerald-300 ring-emerald-500/30"
                          : "bg-red-500/20 text-red-300 ring-red-500/30"
                      }`}>
                        {isCredit ? "▲" : "▼"} {e.entry_type}
                      </span>
                    </td>
                    <td className={`px-4 py-3 font-semibold ${isCredit ? "text-emerald-400" : "text-red-400"}`}>
                      {isCredit ? "+" : "−"}{formatRupees(e.amount_paise)}
                    </td>
                    <td className="px-4 py-3 text-slate-300 max-w-[200px] truncate">{e.description || "—"}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500 max-w-[120px] truncate">{e.reference_id}</td>
                    <td className="px-4 py-3 text-xs text-slate-400">{fmtDate(e.created_at)}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
