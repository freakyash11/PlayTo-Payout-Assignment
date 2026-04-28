/** Convert paise (integer) to a formatted rupee string: ₹1,234.56 */
export const formatRupees = (paise) => {
  if (paise === null || paise === undefined) return "₹0.00";
  return "₹" + (paise / 100).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
};

/** Convert a rupee string typed by the user to integer paise. */
export const rupeesToPaise = (rupeeStr) =>
  Math.round(parseFloat(rupeeStr || "0") * 100);

/** Format an ISO datetime string to a readable local time. */
export const fmtDate = (iso) =>
  new Date(iso).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });

/** Shorten a UUID to first 8 chars for table display. */
export const shortId = (id) => (id ?? "").slice(0, 8).toUpperCase();
