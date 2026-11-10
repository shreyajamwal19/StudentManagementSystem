// Thin API client. The JWT is kept in memory only (never localStorage), so a page refresh logs out.
let token = null;
export const setToken = (t) => { token = t; };

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) throw new Error(`${res.status}: ${typeof data?.detail === "string" ? data.detail : JSON.stringify(data?.detail ?? data)}`);
  return data;
}

export const login = async (username, password) => {
  const r = await api("/auth/login", { method: "POST", body: { username, password } });
  setToken(r.access_token);
  return r;
};
