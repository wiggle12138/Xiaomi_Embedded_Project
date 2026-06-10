export async function getJson(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

export async function postJson(url, payload = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

export async function putJson(url, payload = {}) {
  const res = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

export async function deleteJson(url) {
  const res = await fetch(url, { method: "DELETE" });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}
