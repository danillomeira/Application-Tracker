// Service worker: única peça que fala com a API (token fica aqui, nunca na página).
const DEFAULTS = { apiUrl: "http://localhost:8000", token: "", enabled: true, ignoredDomains: ["mail.google.com", "web.whatsapp.com", "localhost:3100"] };

async function config() {
  const c = await chrome.storage.sync.get(DEFAULTS);
  return { ...DEFAULTS, ...c };
}

async function api(method, path, body) {
  const c = await config();
  if (!c.token) throw new Error("Configure o token da extensão nas opções");
  const res = await fetch(`${c.apiUrl.replace(/\/$/, "")}/api/v1/assistant${path}`, {
    method,
    headers: { Authorization: `Extension ${c.token}`, ...(body ? { "content-type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = `Erro ${res.status}`;
    try { msg = (await res.json()).error?.message ?? msg; } catch {}
    throw new Error(msg);
  }
  return res;
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  (async () => {
    try {
      if (msg.type === "config") return reply({ ok: true, data: await config() });
      if (msg.type === "api") {
        const res = await api(msg.method, msg.path, msg.body);
        return reply({ ok: true, data: await res.json() });
      }
      if (msg.type === "resume") {
        const res = await api("GET", `/resume${msg.jobId ? `?job_id=${msg.jobId}` : ""}`);
        const buf = new Uint8Array(await res.arrayBuffer());
        let bin = "";
        for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
        return reply({ ok: true, data: { b64: btoa(bin), filename: res.headers.get("x-filename") || "curriculo.pdf" } });
      }
      reply({ ok: false, error: "mensagem desconhecida" });
    } catch (e) {
      reply({ ok: false, error: String(e.message || e) });
    }
  })();
  return true;
});
