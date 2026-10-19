// Application Tracker — assistente do navegador (content script).
// Regras: só age na página aberta por você; preenche/sugere; NUNCA envia formulários nem clica em "enviar".
(() => {
  if (window.__trackerAssistant) return;
  window.__trackerAssistant = true;

  const IS_TOP = window === window.top;
  const KNOWN_HOSTS = ["linkedin.com/jobs", "greenhouse.io", "lever.co", "ashbyhq.com", "gupy.io", "myworkdayjobs.com", "smartrecruiters.com",
    "workable.com", "inhire", "solides", "kenoby", "recrutei", "teamtailor.com", "breezy.hr", "jobvite.com", "icims.com", "bamboohr.com",
    "recruitee.com", "vagas.com.br", "infojobs.com.br", "catho.com.br", "remotive.com", "remoteok.com", "himalayas.app", "jobicy.com",
    "weworkremotely.com", "workingnomads.com", "programathor.com.br", "arbeitnow.com"];
  const JOB_WORDS = /(responsibilities|requirements|qualifications|about the role|job description|apply now|responsabilidades|requisitos|qualifica[cç][oõ]es|sobre a vaga|candidate-se|benef[ií]cios|modelo de trabalho)/gi;
  const SUCCESS = /(application (was )?(sent|submitted|received)|thank(s| you) for (applying|your application)|we.ve received your application|candidatura (foi )?(enviada|recebida|realizada|conclu[ií]da)|obrigad[oa] por se candidatar|inscri[cç][aã]o (realizada|conclu[ií]da)|recebemos sua candidatura)/i;
  const SS_KEY = "trackerAssistant";

  const state = { cfg: null, card: null, pageInfo: null, fields: [], lastResolve: null, edits: new Map(), filledKeys: new Set(), reported: false };

  // ---------------- comunicação ----------------
  const bg = (msg) => new Promise((resolve, reject) => chrome.runtime.sendMessage(msg, (r) => (r?.ok ? resolve(r.data) : reject(new Error(r?.error || "sem resposta")))));
  const api = (method, path, body) => bg({ type: "api", method, path, body });
  const session = {
    get: () => { try { return JSON.parse(sessionStorage.getItem(SS_KEY) || "{}"); } catch { return {}; } },
    set: (v) => { try { sessionStorage.setItem(SS_KEY, JSON.stringify({ ...session.get(), ...v })); } catch {} },
  };

  // ---------------- extração de campos (rótulos acessíveis) ----------------
  const txt = (el) => (el?.innerText || el?.textContent || "").replace(/\s+/g, " ").trim();
  const visible = (el) => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  function labelFor(el) {
    const aria = el.getAttribute("aria-label"); if (aria) return aria.trim();
    const lb = el.getAttribute("aria-labelledby");
    if (lb) { const t = lb.split(/\s+/).map((id) => txt(document.getElementById(id))).join(" ").trim(); if (t) return t; }
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return txt(l); }
    const wrap = el.closest("label"); if (wrap) return txt(wrap);
    const fs = el.closest("fieldset"); const lg = fs?.querySelector("legend"); if (lg) return txt(lg);
    const prev = el.closest("div")?.previousElementSibling; if (prev && txt(prev).length < 200) return txt(prev);
    return el.getAttribute("placeholder") || el.name || "";
  }
  const SKIP = /password|senha|card|cart[aã]o|cvv|captcha/i;
  function describe(el, key) {
    const type = (el.getAttribute("type") || "").toLowerCase();
    let kind = el.tagName === "SELECT" ? "select" : el.tagName === "TEXTAREA" ? "textarea" : type || "text";
    if (el.getAttribute("role") === "combobox" && el.tagName === "INPUT") kind = "typeahead";
    if (!["text", "email", "tel", "number", "date", "file", "checkbox", "select", "textarea", "typeahead", "url"].includes(kind)) kind = "text";
    const options = el.tagName === "SELECT" ? [...el.options].filter((o) => o.value && !/^(select|selecione|escolha)/i.test(o.text.trim())).map((o) => o.text.trim()) : [];
    const label = labelFor(el);
    return { key, label, kind: kind === "url" ? "text" : kind, options, required: el.required || el.getAttribute("aria-required") === "true",
      current_value: kind === "checkbox" ? String(el.checked) : el.tagName === "SELECT" ? (el.value ? el.options[el.selectedIndex]?.text?.trim() : null) : kind === "file" ? null : el.value || null };
  }
  function extractFields() {
    const out = []; const seen = new Set(); let i = 0;
    document.querySelectorAll("input, select, textarea").forEach((el) => {
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (["hidden", "submit", "button", "image", "reset", "search", "password"].includes(type) || el.disabled || el.readOnly) return;
      if (type !== "file" && !visible(el)) return;
      if (type === "file" && !(visible(el) || visible(el.closest("label, div, section, form")))) return;
      if (SKIP.test((el.name || "") + (el.id || "") + (el.autocomplete || ""))) return;
      if (type === "radio") {
        const name = el.name || el.id; if (seen.has(name)) return; seen.add(name);
        const group = [...document.querySelectorAll(`input[type=radio][name="${CSS.escape(name)}"]`)];
        const key = el.dataset.trk || `trk${Date.now().toString(36)}_${i++}`;
        group.forEach((r, idx) => { r.dataset.trk = key; r.dataset.trkIdx = idx; });
        const opts = group.map((r) => txt(r.id ? document.querySelector(`label[for="${CSS.escape(r.id)}"]`) : r.closest("label")) || r.value);
        const fs = el.closest("fieldset"); const checked = group.find((r) => r.checked);
        out.push({ key, label: txt(fs?.querySelector("legend")) || labelFor(el), kind: "radio", options: opts, required: group.some((r) => r.required), current_value: checked ? opts[group.indexOf(checked)] : null });
        return;
      }
      const key = el.dataset.trk || `trk${Date.now().toString(36)}_${i++}`;
      el.dataset.trk = key;
      const d = describe(el, key);
      if (d.label) out.push(d);
    });
    return out;
  }
  const byKey = (key) => document.querySelector(`[data-trk="${CSS.escape(key)}"]:not([type=radio])`);

  // ---------------- preenchimento compatível com React/Vue ----------------
  function setNative(el, value) {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    setter ? setter.call(el, value) : (el.value = value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  }
  async function attachResume(el, jobId) {
    const { b64, filename } = await bg({ type: "resume", jobId });
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], filename, { type: "application/pdf" }));
    el.files = dt.files;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }
  function mark(el, color, title) {
    if (!el) return;
    el.style.outline = `2px solid ${color}`;
    el.style.outlineOffset = "1px";
    if (title) el.title = title;
  }
  async function applyValue(field, value, source) {
    if (field.kind === "radio") {
      const idx = field.options.indexOf(value);
      const r = document.querySelector(`input[type=radio][data-trk="${CSS.escape(field.key)}"][data-trk-idx="${idx}"]`);
      if (r) { r.click(); mark(r.closest("fieldset") || r.parentElement, "#16a34a", `Assistente: ${source}`); }
      return !!r;
    }
    const el = byKey(field.key);
    if (!el) return false;
    if (field.kind === "file") {
      if (value === "__resume__") { await attachResume(el, state.card?.job_id); mark(el.closest("div") || el, "#16a34a", "Assistente: currículo anexado"); }
      return true;
    }
    if (field.kind === "checkbox") { if (el.checked !== Boolean(value)) el.click(); mark(el, "#16a34a"); return true; }
    if (field.kind === "select") {
      const opt = [...el.options].find((o) => o.text.trim() === String(value));
      if (!opt) return false;
      setNative(el, opt.value);
    } else {
      setNative(el, String(value));
    }
    mark(el, "#16a34a", `Assistente: ${source}`);
    state.filledKeys.add(field.key);
    return true;
  }

  // ---------------- painel (shadow DOM) ----------------
  let panel, shadow;
  function ensurePanel() {
    if (panel) return;
    panel = document.createElement("div");
    panel.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483646";
    panel.id = "tracker-assistant";
    shadow = panel.attachShadow({ mode: "open" });
    shadow.innerHTML = `<style>
      .box{font:13px system-ui,sans-serif;width:320px;max-height:70vh;overflow:auto;background:#fff;color:#0f172a;border:1px solid #cbd5e1;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.18)}
      .hd{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:#1d4ed8;color:#fff;border-radius:10px 10px 0 0;cursor:pointer}
      .bd{padding:10px}.row{margin:4px 0}.muted{color:#64748b;font-size:12px}.bar{height:6px;background:#e2e8f0;border-radius:3px}.bar>i{display:block;height:6px;border-radius:3px}
      button{border:0;border-radius:6px;padding:6px 10px;margin:4px 4px 0 0;cursor:pointer;background:#1d4ed8;color:#fff;font-size:12px}button.s{background:#e2e8f0;color:#0f172a}
      .tag{display:inline-block;padding:1px 6px;border-radius:9px;font-size:11px;background:#e0e7ff;color:#1d4ed8;margin-right:4px}.ok{color:#16a34a}.bad{color:#b91c1c}
      @media (prefers-color-scheme: dark){.box{background:#111827;color:#e2e8f0;border-color:#334155}.bar{background:#334155}button.s{background:#334155;color:#e2e8f0}}
    </style><div class="box"><div class="hd" id="hd"><b>Assistente</b><span id="tg">–</span></div><div class="bd" id="bd"></div></div>`;
    document.documentElement.appendChild(panel);
    shadow.getElementById("hd").onclick = () => {
      const bd = shadow.getElementById("bd");
      const hidden = bd.style.display === "none";
      bd.style.display = hidden ? "" : "none";
      shadow.getElementById("tg").textContent = hidden ? "–" : "+";
    };
  }
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const bar = (v) => `<div class="bar"><i style="width:${Math.round(v)}%;background:${v >= 60 ? "#16a34a" : v >= 40 ? "#d97706" : "#dc2626"}"></i></div>`;
  function render(extra = "") {
    ensurePanel();
    const c = state.card;
    let html = "";
    if (c?.known) {
      const s = c.score;
      html += `<div class="row"><b>${esc(c.title)}</b><div class="muted">${esc(c.company)} · ${esc(c.location || "")} ${esc(c.work_model || "")}</div></div>`;
      if (s) {
        html += `<div class="row"><span class="tag">${esc({ top: "Prioridade máxima", bet: "Aposta", volume: "Volume", discard: "Descartar", blocked: "Bloqueada" }[s.quadrant] || s.quadrant)}</span></div>`;
        html += `<div class="row">Chance ${Math.round(s.chance)}${bar(s.chance)}</div><div class="row">Atratividade ${Math.round(s.attractiveness)}${bar(s.attractiveness)}</div>`;
        html += s.reasons.slice(0, 3).map((r) => `<div class="row ok">+ ${esc(r)}</div>`).join("");
        html += s.concerns.slice(0, 2).map((r) => `<div class="row bad">− ${esc(r)}</div>`).join("");
        if (s.missing_must?.length) html += `<div class="row muted">Você não tem: ${esc(s.missing_must.join(", "))}</div>`;
        html += `<div class="row muted">Sugestão: ${esc(s.action)}</div>`;
      }
      if (c.responsiveness) html += `<div class="row">Costuma responder: <b>~${Math.round(c.responsiveness.rate * 100)}%</b> <span class="muted">(confiança ${esc(c.responsiveness.confidence)})</span></div>`;
      if (c.reputation) {
        const r = c.reputation;
        html += `<div class="row">Reputação: ${r.rating ? `<b>${r.rating.toFixed(1)}</b> ${esc(r.rating_source || "")}` : "sem nota pública"}${r.layoffs ? ' · <span class="bad">layoff recente</span>' : ""}</div>`;
        if (r.alerts?.length) html += `<div class="row bad">⚠ ${esc(r.alerts.join(", "))}</div>`;
        if (r.ghosting_reports) html += `<div class="row bad">Relatos de candidatos sem retorno: ${r.ghosting_reports}</div>`;
      }
      if (c.application) html += `<div class="row ok">Candidatura: ${esc(c.application.status)}</div>`;
    } else if (state.pageInfo?.looks_like_job) {
      html += `<div class="row">Parece uma vaga que ainda não está no seu acompanhamento.</div><button id="an">Analisar vaga</button>`;
    } else {
      html += `<div class="row muted">Formulário detectado nesta página.</div>`;
    }
    const n = state.fields.length;
    if (n) html += `<div class="row" style="margin-top:8px"><button id="fill">Preencher ${n} campo(s)</button><button class="s" id="ai">Preencher com IA</button></div>`;
    html += `<div class="row"><button class="s" id="sent">Marquei como enviada</button>${c?.known ? `<button class="s" id="open">Abrir no tracker</button>` : ""}</div>`;
    html += extra ? `<div class="row muted">${extra}</div>` : "";
    const bd = shadow.getElementById("bd");
    bd.innerHTML = html;
    shadow.getElementById("an")?.addEventListener("click", analyze);
    shadow.getElementById("fill")?.addEventListener("click", () => fill(false));
    shadow.getElementById("ai")?.addEventListener("click", () => fill(true));
    shadow.getElementById("sent")?.addEventListener("click", () => reportSubmitted(true));
    shadow.getElementById("open")?.addEventListener("click", () => window.open(`${(state.cfg.apiUrl || "").replace(":8000", ":3100")}/vagas/${c.job_id}`, "_blank"));
  }
  function toast(msg) {
    ensurePanel();
    render(esc(msg));
  }

  // ---------------- ações ----------------
  const pageText = () => (document.body?.innerText || "").slice(0, 20000);
  function localLooksRelevant() {
    const url = location.href;
    if (KNOWN_HOSTS.some((h) => url.includes(h))) return true;
    const hits = new Set((pageText().match(JOB_WORDS) || []).map((x) => x.toLowerCase())).size;
    const hasApplyForm = !!document.querySelector("input[type=file], input[type=email], input[autocomplete=email]");
    return hits >= 2 || hasApplyForm;
  }
  async function classify() {
    const info = await api("POST", "/page", { url: location.href, title: document.title, text: pageText(), has_form: state.fields.length > 0, session_job_id: session.get().jobId || null });
    // em login/etapas da candidatura (flow_page) a API devolve a vaga de origem: não troca a URL lembrada da vaga
    if (info.known) { state.card = info; session.set(info.flow_page ? { jobId: info.job_id } : { jobId: info.job_id, jobUrl: location.href, company: info.company, jobTitle: info.title }); }
    else state.pageInfo = info;
    if (info.looks_like_job) session.set({ jobUrl: location.href, pageTitle: document.title });
    if (info.auto_analyze && !info.known) await analyze();
    if (info.success_page) await reportSubmitted(false);
  }
  async function analyze() {
    try {
      toast("Analisando a vaga…");
      state.card = await api("POST", "/analyze", { url: location.href, title: document.title, text: pageText() });
      session.set({ jobId: state.card.job_id, jobUrl: location.href, company: state.card.company, jobTitle: state.card.title });
      render();
    } catch (e) { toast(`Não foi possível analisar: ${e.message}`); }
  }
  async function fill(allowAi) {
    state.fields = extractFields();
    if (!state.fields.length) return toast("Nenhum campo encontrado.");
    toast("Buscando respostas…");
    try {
      const res = await api("POST", "/fields", { url: location.href, job_id: state.card?.job_id || session.get().jobId || null, fields: state.fields, allow_ai: allowAi });
      state.lastResolve = res;
      let filled = 0;
      for (const f of state.fields) {
        const v = res.values[f.key];
        if (v && (await applyValue(f, v.value, v.source))) filled++;
        else if (res.suggestions[f.key]) mark(f.kind === "radio" ? null : byKey(f.key), "#d97706", `Sugestão (confiança baixa): ${res.suggestions[f.key].value}`);
        else if (res.sensitive.includes(f.key)) mark(byKey(f.key), "#d97706", "Pergunta sensível: preencha você");
      }
      const pend = state.fields.length - filled;
      toast(`${filled} campo(s) preenchido(s).${pend ? ` ${pend} para você revisar (contorno laranja).` : ""} Revise e envie você mesmo.`);
    } catch (e) { toast(`Erro: ${e.message}`); }
  }

  // sugestão ao clicar em um campo
  let bubble;
  const cache = new Map();
  let hideTimer;
  function hideBubble() { bubble?.remove(); bubble = null; }
  async function onFocus(e) {
    clearTimeout(hideTimer); // o focusout do campo anterior não pode apagar a sugestão deste
    const el = e.target;
    if (!(el instanceof HTMLElement) || !el.matches("input, select, textarea")) return;
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (["hidden", "password", "file", "submit", "button", "checkbox", "radio"].includes(type) || SKIP.test((el.name || "") + (el.id || ""))) return;
    if (el.value && el.tagName !== "SELECT") return;
    if (!el.dataset.trk) el.dataset.trk = `trk${Date.now().toString(36)}`;
    const field = describe(el, el.dataset.trk);
    if (!field.label) return;
    const show = (s, aiTried) => {
      hideBubble();
      const r = el.getBoundingClientRect();
      bubble = document.createElement("div");
      bubble.style.cssText = `position:fixed;left:${Math.max(4, r.left)}px;top:${r.bottom + 4}px;z-index:2147483647;font:12px system-ui,sans-serif;background:#0f172a;color:#fff;padding:6px 8px;border-radius:6px;max-width:360px;box-shadow:0 4px 12px rgba(0,0,0,.25)`;
      const val = s?.value;
      bubble.innerHTML = val ? `💡 <b>${esc(val).slice(0, 200)}</b> <span style="opacity:.7">(${esc(s.source || "ia")})</span> ` : s?.sensitive ? "🔒 Pergunta sensível: responda você " : "Sem sugestão salva. ";
      if (val) { const b = document.createElement("button"); b.textContent = "Usar"; b.style.cssText = "margin-left:6px;border:0;border-radius:4px;padding:2px 6px;cursor:pointer"; b.onmousedown = (ev) => { ev.preventDefault(); applyValue(field, val, s.source || "sugestão"); hideBubble(); }; bubble.appendChild(b); }
      if (!aiTried && !s?.sensitive) { const b = document.createElement("button"); b.textContent = "✨ IA"; b.style.cssText = "margin-left:6px;border:0;border-radius:4px;padding:2px 6px;cursor:pointer"; b.onmousedown = async (ev) => { ev.preventDefault(); bubble.textContent = "Pensando…"; try { show(await api("POST", "/suggest", { url: location.href, job_id: state.card?.job_id || null, field, allow_ai: true }), true); } catch (er) { bubble.textContent = er.message; } }; bubble.appendChild(b); }
      document.documentElement.appendChild(bubble);
    };
    const ck = `${field.label}|${field.options.join(";")}`;
    try {
      const s = cache.get(ck) ?? (await api("POST", "/suggest", { url: location.href, job_id: state.card?.job_id || session.get().jobId || null, field, allow_ai: false }));
      cache.set(ck, s);
      if (document.activeElement === el) show(s, false);
    } catch { /* silencioso */ }
  }

  // aprendizado: o que você digitou/escolheu
  function onChange(e) {
    const el = e.target;
    if (!(el instanceof HTMLElement) || !el.matches("input, select, textarea")) return;
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (["password", "hidden", "file"].includes(type) || SKIP.test((el.name || "") + (el.id || ""))) return;
    let label, value, kind = "text", options = [];
    if (type === "radio") { const fs = el.closest("fieldset"); label = txt(fs?.querySelector("legend")) || labelFor(el); value = txt(el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`) : el.closest("label")) || el.value; kind = "radio"; }
    else { const d = describe(el, el.dataset.trk || "x"); label = d.label; value = d.kind === "checkbox" ? el.checked : d.current_value; kind = d.kind; options = d.options; }
    if (label && value !== null && value !== "") {
      state.edits.set(label, { question: label, value, field_kind: kind, options });
      session.set({ answers: [...state.edits.values()] });
    }
  }

  // detecção de envio
  async function reportSubmitted(manual) {
    if (state.reported) return;
    const s = session.get();
    if (!manual && !s.jobUrl && !state.card) return;
    state.reported = true;
    try {
      const res = await api("POST", "/submitted", {
        url: s.jobUrl || location.href, title: s.pageTitle || document.title, text: manual ? pageText() : "",
        job_id: state.card?.job_id || s.jobId || null, company: s.company || null, job_title: s.jobTitle || null,
        answers: s.answers || [...state.edits.values()],
      });
      session.set({ answers: [], submittedAppId: res.application_id });
      toast(res.already ? "Esta candidatura já estava no acompanhamento." : "✓ Candidatura adicionada ao seu acompanhamento.");
    } catch (e) { state.reported = false; toast(`Erro ao registrar: ${e.message}`); }
  }
  function watchSuccess() {
    let t;
    const check = () => {
      clearTimeout(t);
      t = setTimeout(() => {
        const s = session.get();
        if ((s.formSubmitted || state.edits.size || state.filledKeys.size || state.card) && SUCCESS.test(pageText())) reportSubmitted(false);
      }, 800);
    };
    new MutationObserver(check).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
    document.addEventListener("submit", () => session.set({ formSubmitted: Date.now(), answers: [...state.edits.values()] }), true);
  }

  // ---------------- início ----------------
  let wired = false;
  async function start() {
    state.cfg = await bg({ type: "config" }).catch(() => null);
    if (!state.cfg?.enabled || !state.cfg.token) return;
    if ((state.cfg.ignoredDomains || []).some((d) => location.host.includes(d))) return;
    if (!wired) {
      wired = true;
      document.addEventListener("focusin", onFocus, true);
      document.addEventListener("focusout", () => { clearTimeout(hideTimer); hideTimer = setTimeout(hideBubble, 200); }, true);
      document.addEventListener("change", onChange, true);
      watchSuccess();
    }
    if (SUCCESS.test(pageText()) && session.get().jobUrl) { await reportSubmitted(false); return; }
    state.fields = extractFields();
    if (!localLooksRelevant() && !state.fields.some((f) => f.kind === "file" || /e-?mail|curr[ií]culo|resume|cv/i.test(f.label))) return;
    if (!IS_TOP && !state.fields.length) return;
    try { await classify(); } catch (e) { state.pageInfo = { looks_like_job: false }; }
    if (state.card || state.pageInfo?.looks_like_job || state.fields.length) render();
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "tracker:show-panel") { state.fields = extractFields(); classify().catch(() => {}).finally(() => render()); }
    if (msg.type === "tracker:fill") fill(false);
  });

  // SPAs (LinkedIn etc.) mudam de URL sem recarregar
  let lastUrl = location.href;
  setInterval(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      state.card = null; state.pageInfo = null; state.reported = false; state.filledKeys.clear();
      setTimeout(start, 1200);
    }
  }, 1000);

  setTimeout(start, 1200);
})();
