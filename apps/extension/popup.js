const D = globalThis.TRACKER_DEFAULTS;
const $ = (id) => document.getElementById(id);
let cfg = { ...D };
let tab = null;
let host = "";
let hasToken = false;

// só o quadro principal da aba (iframes não abrem outro painel)
const send = async (type) => {
  if (tab?.id) chrome.tabs.sendMessage(tab.id, { type }, { frameId: 0 }).catch(() => {});
  window.close();
};
const setStatus = (cls, text) => { $("status").className = `pill ${cls}`; $("status").innerHTML = "<i></i>"; $("status").append(text); };
const isPaused = () => (cfg.pausedUntil || 0) > Date.now();
const hhmm = (ts) => new Date(ts).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

function paint() {
  $("enabled").checked = cfg.enabled;
  $("autoFill").checked = cfg.autoFill;
  $("attachResume").checked = cfg.attachResume !== false;
  const off = (cfg.ignoredDomains || []).some((d) => host && host.includes(d));
  $("site").checked = !off;
  $("host").textContent = host || "página do navegador";
  $("site").disabled = !host;
  const blocked = !cfg.enabled || off || !host || !hasToken || isPaused();
  for (const id of ["panel", "fill", "ai"]) $(id).disabled = blocked;
  $("pause").textContent = isPaused() ? "Retomar" : "Pausar 1h";
  $("pausedNote").style.display = isPaused() ? "block" : "none";
  $("pausedNote").textContent = isPaused() ? `Pausado até ${hhmm(cfg.pausedUntil)}. Nada é lido nem preenchido até lá.` : "";
}

async function stats() {
  const { stats: s } = await chrome.storage.local.get({ stats: {} });
  const today = new Date().toISOString().slice(0, 10);
  const v = s.day === today ? s : {};
  $("sFilled").textContent = v.filled || 0;
  $("sAi").textContent = v.ai || 0;
  $("sApps").textContent = v.apps || 0;
}

async function init() {
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try { host = tab?.url && /^https?:/.test(tab.url) ? new URL(tab.url).host : ""; } catch { host = ""; }
  cfg = { ...D, ...(await chrome.storage.sync.get(D)) };
  hasToken = !!(await chrome.storage.local.get({ token: "" })).token || !!(await chrome.storage.sync.get({ token: "" })).token;
  paint();
  stats();
  if (!hasToken) return setStatus("warn", "Configure o token");
  if (!cfg.enabled) return setStatus("", "Desligado");
  if (isPaused()) return setStatus("warn", "Pausado");
  chrome.runtime.sendMessage({ type: "ping" }, (r) => {
    if (r?.ok) setStatus("ok", `Conectado · ${(r.data.name || "").split(" ")[0] || "ok"}`);
    else setStatus("bad", r?.error?.includes("Token") ? "Token inválido" : "App desligado");
  });
}

$("enabled").onchange = async (e) => { cfg.enabled = e.target.checked; await chrome.storage.sync.set({ enabled: cfg.enabled }); init(); };
$("autoFill").onchange = async (e) => { cfg.autoFill = e.target.checked; await chrome.storage.sync.set({ autoFill: cfg.autoFill }); };
$("attachResume").onchange = async (e) => { cfg.attachResume = e.target.checked; await chrome.storage.sync.set({ attachResume: cfg.attachResume }); };
$("site").onchange = async (e) => {
  const list = (cfg.ignoredDomains || []).filter((d) => !host.includes(d));
  if (!e.target.checked) list.push(host);
  cfg.ignoredDomains = list;
  await chrome.storage.sync.set({ ignoredDomains: list });
  paint();
};
$("pause").onclick = async () => {
  cfg.pausedUntil = isPaused() ? 0 : Date.now() + 60 * 60 * 1000;
  await chrome.storage.sync.set({ pausedUntil: cfg.pausedUntil });
  if (cfg.pausedUntil) chrome.alarms?.create("resume", { when: cfg.pausedUntil }); else chrome.alarms?.clear("resume");
  init();
};
$("panel").onclick = () => send("tracker:show-panel");
$("fill").onclick = () => send("tracker:fill");
$("ai").onclick = () => send("tracker:ai");
$("dash").onclick = () => { chrome.runtime.sendMessage({ type: "openDashboard", path: "/vagas" }); window.close(); };
$("opts").onclick = () => chrome.runtime.openOptionsPage();
$("keys").onclick = () => chrome.tabs.create({ url: "chrome://extensions/shortcuts" });
init();
