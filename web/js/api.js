// Thin fetch layer. Served by the FastAPI bridge the base is same-origin;
// opened as a plain file it falls back to the default local API port.

const API_BASE = (location.protocol === 'file:') ? 'http://localhost:8787' : '';

export async function apiGet(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

export async function apiPost(path, body) {
  const res = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}
