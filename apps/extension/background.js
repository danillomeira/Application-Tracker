// Service worker: única peça que fala com a API (token fica aqui, nunca na página).
const DEFAULTS = { apiUrl: "http://localhost:8000", token: "", enabled: true, autoFill: true, ignoredDomains: ["mail.google.com", "web.whatsapp.com", "localhost:3100"] };
const logos = new Map(); // cache por empresa durante a sessão do navegador
const DISCOVERY_ALARM = "tracker-linkedin-discovery";
const DISCOVERY_TIMEOUT_PREFIX = "tracker-linkedin-timeout-";
const DISCOVERY_TIMEOUT_MINUTES = 10;

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
        if (tabId != null) await finishDiscovery(tabId, msg);
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

async function reportDiscovery(search, result) {
  if (!search?.id) return;
  await api("POST", `/discovery/${encodeURIComponent(search.id)}/complete`, result).catch((error) => {
    console.error("Could not report LinkedIn discovery result:", error);
  });
}

async function finishDiscovery(tabId, result = {}) {
  const { discoveryTabs = {} } = await chrome.storage.local.get("discoveryTabs");
  const search = discoveryTabs[String(tabId)];
  if (!search) return;
  delete discoveryTabs[String(tabId)];
  await chrome.storage.local.set({ discoveryTabs });
  await chrome.alarms.clear(`${DISCOVERY_TIMEOUT_PREFIX}${tabId}`);
  const failed = Boolean(result.error);
  await reportDiscovery(search, {
    status: failed ? "failed" : "completed",
    count: Number(result.count) || 0,
    created: Number(result.created) || 0,
    existing: Number(result.existing) || 0,
    ...(failed && { error: String(result.error).slice(0, 300) }),
  });
  if (failed) {
    console.error("LinkedIn discovery failed:", result.error);
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
      let tab;
      try {
        // Registra a busca antes de navegar para não perder a associação se o content script iniciar rápido.
        tab = await chrome.tabs.create({ url: "about:blank", active: false });
        discoveryTabs[String(tab.id)] = search;
        await chrome.storage.local.set({ discoveryTabs });
        await chrome.alarms.create(`${DISCOVERY_TIMEOUT_PREFIX}${tab.id}`, { delayInMinutes: DISCOVERY_TIMEOUT_MINUTES });
        await chrome.tabs.update(tab.id, { url: search.url });
      } catch (error) {
        if (tab?.id != null) await finishDiscovery(tab.id, { error: String(error.message || error) });
        else await reportDiscovery(search, { status: "failed", error: String(error.message || error) });
      }
    }
  } catch (error) {
    if (!String(error.message).includes("Configure o token")) console.error("LinkedIn discovery polling failed:", error);
  }
}

function ensureDiscoveryAlarm() {
  void chrome.alarms.get(DISCOVERY_ALARM).then((alarm) => {
    if (alarm?.periodInMinutes !== 0.5) {
      chrome.alarms.create(DISCOVERY_ALARM, { periodInMinutes: 0.5 });
    }
  });
}

ensureDiscoveryAlarm();
chrome.runtime.onInstalled.addListener(ensureDiscoveryAlarm);
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "sync" && ["apiUrl", "enabled", "token"].some((key) => key in changes)) {
    void pollLinkedinDiscoveries();
  }
});
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === DISCOVERY_ALARM) void pollLinkedinDiscoveries();
  else if (alarm.name.startsWith(DISCOVERY_TIMEOUT_PREFIX)) {
    const tabId = Number(alarm.name.slice(DISCOVERY_TIMEOUT_PREFIX.length));
    if (Number.isInteger(tabId)) void finishDiscovery(tabId, { error: "A página do LinkedIn demorou demais para responder." });
  }
});
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete" || !tab.url) return;
  // A discovery tab is created at about:blank before navigating to LinkedIn.
  // Ignore that initial completion; it is not a LinkedIn redirect.
  if (!/^https?:\/\//i.test(tab.url)) return;

  let currentUrl;
  try {
    currentUrl = new URL(tab.url);
  } catch {
    return;
  }

  const isLinkedin = currentUrl.hostname === "linkedin.com" || currentUrl.hostname.endsWith(".linkedin.com");
  const isJobsSearch = /^\/jobs\/(search(?:-results)?|collections)(?:\/|$)/i.test(currentUrl.pathname);
  if (isLinkedin && isJobsSearch) return;

  void chrome.storage.local.get("discoveryTabs").then(({ discoveryTabs = {} }) => {
    const search = discoveryTabs[String(tabId)];
    if (!search) return;

    // LinkedIn can route unauthenticated users through several intermediate
    // pages (not all of them have /login in the path). Keep its page open so the
    // user can authenticate; its redirect should return to the requested search.
    if (isLinkedin) {
      void chrome.alarms.create(`${DISCOVERY_TIMEOUT_PREFIX}${tabId}`, { delayInMinutes: DISCOVERY_TIMEOUT_MINUTES });
      void chrome.tabs.update(tabId, { active: true }).catch(() => {});
      void chrome.action.setBadgeText({ text: "!" });
      void chrome.action.setBadgeBackgroundColor({ color: "#0284c7" });
      return;
    }

    const destination = `${currentUrl.hostname}${currentUrl.pathname}`.slice(0, 160);
    void finishDiscovery(tabId, { error: `O navegador saiu do LinkedIn para ${destination}. Verifique a sessão e tente novamente.` });
  });
});
chrome.tabs.onRemoved.addListener((tabId) => {
  void chrome.storage.local.get("discoveryTabs").then(({ discoveryTabs = {} }) => {
    if (discoveryTabs[String(tabId)]) {
      void finishDiscovery(tabId, { error: "A aba de busca do LinkedIn foi fechada antes da importação." });
    }
  });
});
chrome.runtime.onStartup.addListener(() => {
  ensureDiscoveryAlarm();
  void pollLinkedinDiscoveries();
});
