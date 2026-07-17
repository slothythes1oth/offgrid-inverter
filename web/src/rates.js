// Edited TOU rates live in localStorage; the API stays read-only and cost
// math stays server-side (rates travel as query params). Empty = use the
// config defaults baked into the backend.

const KEY = "solarmon.rates";

export function getRates() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {};
  } catch {
    return {};
  }
}

export function setRates(r) {
  const clean = Object.fromEntries(
    Object.entries(r).filter(([, v]) => v !== "" && v != null && !Number.isNaN(+v))
  );
  localStorage.setItem(KEY, JSON.stringify(clean));
}

export function clearRates() {
  localStorage.removeItem(KEY);
}

// Query-string suffix for the tou endpoints ("" when using defaults).
export function rateQS() {
  const r = getRates();
  const parts = [];
  if (r.off != null) parts.push(`off=${r.off}`);
  if (r.mid != null) parts.push(`mid=${r.mid}`);
  if (r.on != null) parts.push(`on=${r.on}`);
  if (r.all_in != null) parts.push(`all_in=${r.all_in}`);
  return parts.length ? `&${parts.join("&")}` : "";
}
