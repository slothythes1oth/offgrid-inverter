// Small fetch helpers. All read-only; the backend has no write endpoints.

export async function getJSON(path) {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export const getSettings = () => getJSON("/api/settings");
export const getRecent = (windowS = 900) =>
  getJSON(`/api/samples/recent?window_s=${windowS}`);
