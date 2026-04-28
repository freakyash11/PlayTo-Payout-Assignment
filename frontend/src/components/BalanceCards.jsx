import { formatRupees } from "../utils";

const cardConfig = {
  available: {
    label: "Available Balance",
    key: "available_paise",
    icon: "💰",
    gradient: "from-emerald-500 to-teal-600",
    ring: "ring-emerald-400/30",
    badge: "bg-emerald-400/20 text-emerald-100",
    badgeText: "Spendable",
  },
  held: {
    label: "Held Balance",
    key: "held_paise",
    icon: "⏳",
    gradient: "from-amber-500 to-orange-600",
    ring: "ring-amber-400/30",
    badge: "bg-amber-400/20 text-amber-100",
    badgeText: "In Transit",
  },
  net: {
    label: "Net Balance",
    key: "net_balance_paise",
    icon: "📊",
    gradient: "from-blue-500 to-indigo-600",
    ring: "ring-blue-400/30",
    badge: "bg-blue-400/20 text-blue-100",
    badgeText: "Total Credits",
  },
};

function Card({ cfg, paise, loading }) {
  return (
    <div className={`relative overflow-hidden rounded-2xl bg-gradient-to-br ${cfg.gradient} ring-1 ${cfg.ring} p-6 shadow-xl flex flex-col gap-3`}>
      {/* background glow */}
      <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full bg-white/10 blur-2xl" />

      <div className="flex items-center justify-between">
        <span className="text-2xl">{cfg.icon}</span>
        <span className={`rounded-full px-3 py-0.5 text-xs font-semibold ${cfg.badge}`}>
          {cfg.badgeText}
        </span>
      </div>

      <p className="text-sm font-medium text-white/70">{cfg.label}</p>

      {loading ? (
        <div className="h-9 w-36 animate-pulse rounded-lg bg-white/20" />
      ) : (
        <p className="text-3xl font-bold tracking-tight text-white">
          {formatRupees(paise)}
        </p>
      )}
    </div>
  );
}

export default function BalanceCards({ balance, loading }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {Object.entries(cardConfig).map(([k, cfg]) => (
        <Card
          key={k}
          cfg={cfg}
          paise={balance?.[cfg.key] ?? 0}
          loading={loading}
        />
      ))}
    </div>
  );
}
