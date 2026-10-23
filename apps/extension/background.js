// Service worker: única peça que fala com a API (token fica aqui, nunca na página).
const DEFAULTS = { apiUrl: "http://localhost:8000", token: "", enabled: true, autoFill: true, ignoredDomains: ["mail.google.com", "web.whatsapp.com", "localhost:3100"] };
const logos = new Map(); // cache por empresa durante a sessão do navegador
const DISCOVERY_ALARM = "tracker-linkedin-discovery";

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
      if (msg.type === "linkedinDiscoveryInfo") {
        const tabId = _sender.tab?.id;
        const { discoveryTabs = {} } = await chrome.storage.local.get("discoveryTabs");
        return reply({ ok: true, data: tabId == null ? null : discoveryTabs[String(tabId)] || null });
      }
      if (msg.type === "linkedinDiscoveryComplete") {
        const tabId = _sender.tab?.id;
        if (tabId != null) await finishDiscovery(tabId, msg.error);
        return reply({ ok: true, data: null });
      }
      if (msg.type === "config") return reply({ ok: true, data: await config() });
      if (msg.type === "api") {
        const res = await api(msg.method, msg.path, msg.body);
        return reply({ ok: true, data: await res.json() });
      }
      if (msg.type === "logo") {
        if (logos.has(msg.companyId)) return reply({ ok: true, data: logos.get(msg.companyId) });
        const res = await api("GET", `/logo?company_id=${encodeURIComponent(msg.companyId)}`);
        const buf = new Uint8Array(await res.arrayBuffer());
        let bin = "";
        for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
        const url = `data:${res.headers.get("content-type") || "image/png"};base64,${btoa(bin)}`;
        logos.set(msg.companyId, url);
        return reply({ ok: true, data: url });
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

async function finishDiscovery(tabId, error) {
  const { discoveryTabs = {} } = await chrome.storage.local.get("discoveryTabs");
  delete discoveryTabs[String(tabId)];
  await chrome.storage.local.set({ discoveryTabs });
  if (error) {
    console.error("LinkedIn discovery failed:", error);
    await chrome.action.setBadgeText({ text: "!" });
    await chrome.action.setBadgeBackgroundColor({ color: "#dc2626" });
  } else {
    await chrome.action.setBadgeText({ text: "" });
  }
  await chrome.tabs.remove(tabId).catch(() => {});
}

async function pollLinkedinDiscoveries() {
  try {
    const c = await config();
    if (!c.enabled || !c.token) return;
    const res = await api("GET", "/discovery/due");
    const searches = await res.json();
    const { discoveryTabs = {} } = await chrome.storage.local.get("discoveryTabs");
    for (const search of searches) {
      const tab = await chrome.tabs.create({ url: search.url, active: false });
      discoveryTabs[String(tab.id)] = search;
    }
    await chrome.storage.local.set({ discoveryTabs });
  } catch (error) {
    if (!String(error.message).includes("Configure o token")) console.error("LinkedIn discovery polling failed:", error);
  }
}

function ensureDiscoveryAlarm() {
  void chrome.alarms.get(DISCOVERY_ALARM).then((alarm) => {
    if (!alarm) chrome.alarms.create(DISCOVERY_ALARM, { periodInMinutes: 5 });
  });
}

ensureDiscoveryAlarm();
chrome.runtime.onInstalled.addListener(ensureDiscoveryAlarm);
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === DISCOVERY_ALARM) void pollLinkedinDiscoveries();
});
chrome.runtime.onStartup.addListener(() => {
  ensureDiscoveryAlarm();
  void pollLinkedinDiscoveries();
});
