// Application Tracker — assistente do navegador (content script).
// Regras: só age na página aberta por você; preenche e sugere; NUNCA envia formulários nem clica em "enviar".
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
  const SKIP = /password|senha|card.?number|cart[aã]o|cvv|captcha|search|busca|pesquis/i;

  const state = {
    filling: false,
    cfg: null, card: null, pageInfo: null, fields: [], status: new Map(), edits: new Map(), reported: false,
    busy: false, msg: "", minimized: false, logo: null, linkedinList: [],
  };
  let linkedinDiscoveryRunning = false;

  // ---------------- comunicação ----------------
  const bg = (msg) => new Promise((resolve, reject) => chrome.runtime.sendMessage(msg, (r) => (r?.ok ? resolve(r.data) : reject(new Error(r?.error || "sem resposta")))));
  const api = (method, path, body) => bg({ type: "api", method, path, body });
  const session = {
    get: () => { try { return JSON.parse(sessionStorage.getItem(SS_KEY) || "{}"); } catch { return {}; } },
    set: (v) => { try { sessionStorage.setItem(SS_KEY, JSON.stringify({ ...session.get(), ...v })); } catch {} },
  };
  const jobId = () => state.card?.job_id || session.get().jobId || null;

  // ---------------- texto e comparação ----------------
  const txt = (el) => (el?.innerText || el?.textContent || "").replace(/\s+/g, " ").trim();
  const norm = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9+#.]+/g, " ").trim();
  const visible = (el) => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== "hidden";
  // equivalências PT/EN mais comuns em formulários
  const SYN = [
    ["sim", "yes", "true"], ["nao", "no", "false"],
    ["fluente", "fluent", "nativo", "native", "proficient"], ["avancado", "advanced"], ["intermediario", "intermediate"], ["basico", "basic", "beginner", "iniciante"],
    ["remoto", "remote"], ["hibrido", "hybrid"], ["presencial", "on site", "onsite", "in office"],
    ["masculino", "male", "homem"], ["feminino", "female", "mulher"],
    ["ensino superior completo", "bachelor", "bacharelado", "graduacao", "superior completo", "bachelor s degree"],
    ["pos graduacao", "postgraduate", "especializacao", "mba"], ["mestrado", "master", "master s degree"], ["doutorado", "doctorate", "phd"],
    ["clt", "full time employee", "employee"], ["pj", "contractor", "pessoa juridica"],
  ];
  const synOf = (s) => { const n = norm(s); return SYN.find((g) => g.includes(n)) || [n]; };

  /** Melhor opção para um valor: exata → sinônimo → contém → faixa numérica ("3-5 anos"). */
  function bestOption(options, value) {
    const v = norm(value);
    if (!v) return -1;
    const vs = synOf(value);
    let idx = options.findIndex((o) => norm(o) === v);
    if (idx >= 0) return idx;
    idx = options.findIndex((o) => vs.includes(norm(o)) || synOf(o).some((x) => vs.includes(x)));
    if (idx >= 0) return idx;
    idx = options.findIndex((o) => { const n = norm(o); return n && (n.includes(v) || v.includes(n)) && Math.min(n.length, v.length) >= 2; });
    if (idx >= 0) return idx;
    const num = parseFloat(String(value).replace(",", "."));
    if (!Number.isNaN(num)) {
      idx = options.findIndex((o) => {
        const m = norm(o).match(/(\d+(?:\.\d+)?)\s*(?:a|-|to|ate)\s*(\d+(?:\.\d+)?)/);
        if (m) return num >= +m[1] && num <= +m[2];
        const plus = norm(o).match(/(\d+)\s*\+|mais de (\d+)|more than (\d+)|acima de (\d+)/);
        if (plus) return num >= +(plus[1] || plus[2] || plus[3] || plus[4]);
        const less = norm(o).match(/menos de (\d+)|less than (\d+)|ate (\d+)|up to (\d+)/);
        if (less) return num < +(less[1] || less[2] || less[3] || less[4]);
        return false;
      });
    }
    return idx;
  }

  // ---------------- leitura dos campos (rótulos acessíveis) ----------------
  function labelFor(el) {
    const aria = el.getAttribute("aria-label"); if (aria && aria.length > 1) return aria.trim();
    const lb = el.getAttribute("aria-labelledby");
    if (lb) { const t = lb.split(/\s+/).map((id) => txt(document.getElementById(id))).join(" ").trim(); if (t) return t; }
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return txt(l); }
    const wrap = el.closest("label"); if (wrap && txt(wrap)) return txt(wrap);
    const fs = el.closest("fieldset"); const lg = fs?.querySelector("legend"); if (lg) return txt(lg);
    // procura o texto mais próximo acima (formulários sem <label>)
    let node = el;
    for (let depth = 0; depth < 4 && node; depth++) {
      let prev = node.previousElementSibling;
      while (prev) {
        const t = txt(prev);
        if (t && t.length < 220 && !prev.matches("input,select,textarea,button")) return t;
        prev = prev.previousElementSibling;
      }
      node = node.parentElement;
    }
    return el.getAttribute("placeholder") || el.name || "";
  }
  function radioOptionLabel(r) {
    return txt(r.id ? document.querySelector(`label[for="${CSS.escape(r.id)}"]`) : null) || txt(r.closest("label")) || r.getAttribute("aria-label") || r.value;
  }
  function groupQuestion(first) {
    const fs = first.closest("fieldset"); const lg = fs?.querySelector("legend"); if (lg) return txt(lg);
    const rg = first.closest('[role="radiogroup"]');
    if (rg) { const l = rg.getAttribute("aria-label") || txt(document.getElementById(rg.getAttribute("aria-labelledby") || "")); if (l) return l; }
    const container = first.closest("div, li, section");
    let prev = container?.previousElementSibling;
    if (prev && txt(prev).length < 220) return txt(prev);
    return labelFor(first);
  }
  function kindOf(el) {
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (el.tagName === "SELECT") return "select";
    if (el.tagName === "TEXTAREA") return "textarea";
    if (el.getAttribute("role") === "combobox" || el.getAttribute("aria-autocomplete") === "list" || el.getAttribute("aria-haspopup") === "listbox") return "typeahead";
    if (["email", "tel", "number", "date", "file", "checkbox"].includes(type)) return type;
    return "text";
  }
  let seq = 0;
  const newKey = () => `trk${Date.now().toString(36)}_${seq++}`;
  function extractFields() {
    const out = []; const seen = new Set();
    document.querySelectorAll("input, select, textarea").forEach((el) => {
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (["hidden", "submit", "button", "image", "reset", "password"].includes(type) || el.disabled || el.readOnly) return;
      if (el.closest("#tracker-assistant")) return;
      if (type !== "file" && !visible(el)) return;
      if (type === "file" && !(visible(el) || visible(el.closest("label, div, section, form")))) return;
      if (SKIP.test(`${el.name || ""} ${el.id || ""} ${el.autocomplete || ""} ${type}`)) return;
      if (type === "radio") {
        const name = el.name || el.id; if (!name || seen.has(name)) return; seen.add(name);
        const group = [...document.querySelectorAll(`input[type=radio][name="${CSS.escape(name)}"]`)];
        const key = el.dataset.trk || newKey();
        group.forEach((r, idx) => { r.dataset.trk = key; r.dataset.trkIdx = idx; });
        const opts = group.map(radioOptionLabel);
        const checked = group.find((r) => r.checked);
        out.push({ key, label: groupQuestion(el), kind: "radio", options: opts, required: group.some((r) => r.required), current_value: checked ? opts[group.indexOf(checked)] : null });
        return;
      }
      const key = el.dataset.trk || newKey();
      el.dataset.trk = key;
      const kind = kindOf(el);
      const options = kind === "select" ? [...el.options].filter((o) => o.value && !/^(select|selecione|escolha|--)/i.test(o.text.trim())).map((o) => o.text.trim()) : [];
      const label = labelFor(el);
      if (!label) return;
      out.push({ key, label, kind, options, required: el.required || el.getAttribute("aria-required") === "true",
        current_value: kind === "checkbox" ? String(el.checked) : kind === "select" ? (el.value ? el.options[el.selectedIndex]?.text?.trim() : null) : kind === "file" ? (el.files?.length ? el.files[0].name : null) : el.value || null });
    });
    return out;
  }
  const byKey = (key) => document.querySelector(`[data-trk="${CSS.escape(key)}"]:not([type=radio])`);
  const radiosOf = (key) => [...document.querySelectorAll(`input[type=radio][data-trk="${CSS.escape(key)}"]`)];

  // ---------------- preenchimento robusto (React, Vue, Angular, máscaras) ----------------
  function nativeSet(el, value) {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    setter ? setter.call(el, value) : (el.value = value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }
  /** Simula a digitação (o mesmo caminho de colar texto): frameworks e máscaras aceitam. */
  function typeInto(el, value) {
    const v = String(value);
    try {
      el.focus({ preventScroll: true });
      if (typeof el.select === "function") el.select();
      const ok = document.execCommand("insertText", false, v);
      if (ok && el.value && el.value.replace(/\D/g, "").length >= Math.min(1, v.replace(/\D/g, "").length)) {
        el.dispatchEvent(new Event("change", { bubbles: true }));
        return true;
      }
    } catch {}
    nativeSet(el, v);
    return !!el.value;
  }
  async function attachResume(el) {
    const { b64, filename } = await bg({ type: "resume", jobId: jobId() });
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], filename, { type: "application/pdf" }));
    el.files = dt.files;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return filename;
  }
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function pickFromListbox(value) {
    for (let i = 0; i < 8; i++) {
      await sleep(150);
      const opts = [...document.querySelectorAll('[role="option"]')].filter(visible);
      if (opts.length) {
        const idx = bestOption(opts.map(txt), value);
        if (idx >= 0) { opts[idx].scrollIntoView({ block: "nearest" }); opts[idx].click(); return true; }
      }
    }
    return false;
  }
  function paint(el, tone) {
    const target = el?.closest?.("fieldset") || el;
    if (!target?.style) return;
    target.style.outline = `2px solid ${tone === "ok" ? "#16a34a" : tone === "ai" ? "#2563eb" : "#d97706"}`;
    target.style.outlineOffset = "2px";
    target.style.borderRadius = target.style.borderRadius || "6px";
  }

  /** Coloca o valor no campo. Devolve true se ficou preenchido. */
  async function setValue(field, value) {
    if (value == null || value === "") return false;
    if (field.kind === "radio") {
      const group = radiosOf(field.key);
      const idx = bestOption(group.map(radioOptionLabel), value);
      if (idx < 0) return false;
      const r = group[idx];
      const lab = r.id ? document.querySelector(`label[for="${CSS.escape(r.id)}"]`) : r.closest("label");
      (lab || r).click();
      if (!r.checked) r.click();
      return r.checked;
    }
    const el = byKey(field.key);
    if (!el) return false;
    if (field.kind === "file") { if (value === "__resume__" && !el.files?.length) await attachResume(el); return !!el.files?.length; }
    if (field.kind === "checkbox") {
      const want = ["true", "sim", "yes", "1", "on"].includes(norm(value));
      if (el.checked !== want) el.click();
      return el.checked === want;
    }
    if (field.kind === "select") {
      const opts = [...el.options];
      const idx = bestOption(opts.map((o) => o.text.trim()), value);
      if (idx < 0) return false;
      nativeSet(el, opts[idx].value);
      return true;
    }
    if (field.kind === "typeahead") {
      typeInto(el, value);
      await pickFromListbox(value);
      return !!el.value || !!el.closest("[class*=select]")?.querySelector("[class*=single-value],[class*=singleValue]");
    }
    if (field.kind === "date" && /^\d{2}\/\d{2}\/\d{4}$/.test(String(value))) {
      const [d, m, y] = String(value).split("/");
      nativeSet(el, `${y}-${m}-${d}`);
      return !!el.value;
    }
    return typeInto(el, value);
  }
  const isEmpty = (field) => {
    if (field.kind === "radio") return !radiosOf(field.key).some((r) => r.checked);
    const el = byKey(field.key);
    if (!el) return false;
    if (field.kind === "file") return !el.files?.length;
    if (field.kind === "checkbox") return false; // checkbox só por pedido explícito
    return !el.value;
  };

  // ---------------- preenchimento automático ----------------
  // status por campo: filled (verde) | ai (azul, revisar) | suggestion (laranja) | sensitive | empty
  async function fillFields(fields, allowAi) {
    if (!fields.length) return { filled: 0 };
    const res = await api("POST", "/fields", { url: location.href, job_id: jobId(), fields, allow_ai: allowAi });
    const before = document.activeElement;
    state.filling = true; // ignora os focos causados pelo próprio preenchimento (sem bolha, sem pular a tela)
    try {
      return await applyResults(fields, res, allowAi);
    } finally {
      state.filling = false;
      if (before && before !== document.body && before.isConnected) before.focus({ preventScroll: true });
      else if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    }
  }
  async function applyResults(fields, res, allowAi) {
    let filled = 0;
    for (const f of fields) {
      const known = res.values[f.key];
      const sug = res.suggestions[f.key];
      const prev = state.status.get(f.key);
      if (known && isEmpty(f) && (await setValue(f, known.value))) {
        filled++;
        state.status.set(f.key, { label: f.label, status: "filled", value: known.value, source: known.source });
        paint(f.kind === "radio" ? radiosOf(f.key)[0] : byKey(f.key), "ok");
      } else if (sug && allowAi && isEmpty(f) && (await setValue(f, sug.value))) {
        filled++;
        state.status.set(f.key, { label: f.label, status: "ai", value: sug.value, source: "IA" });
        paint(f.kind === "radio" ? radiosOf(f.key)[0] : byKey(f.key), "ai");
      } else if (res.sensitive.includes(f.key)) {
        state.status.set(f.key, { label: f.label, status: "sensitive" });
      } else if (!isEmpty(f)) {
        state.status.set(f.key, { label: f.label, status: prev?.status === "ai" ? "ai" : "filled", value: f.current_value, source: prev?.source || "você" });
      } else {
        state.status.set(f.key, { label: f.label, status: sug ? "suggestion" : "empty", value: sug?.value });
      }
    }
    return { filled };
  }
  async function autoFill(onlyNew) {
    if (state.busy) return;
    const all = extractFields();
    state.fields = all;
    const todo = onlyNew ? all.filter((f) => !state.status.has(f.key)) : all;
    if (!todo.length) return render();
    state.busy = true;
    render("Preenchendo com o seu perfil…");
    try {
      const { filled } = await fillFields(todo, false);
      state.msg = filled ? `${filled} campo(s) preenchido(s) automaticamente. Confira antes de enviar.` : "Nada para preencher automaticamente aqui.";
    } catch (e) { state.msg = `Não consegui preencher: ${e.message}`; }
    state.busy = false;
    render();
  }
  async function aiFill() {
    if (state.busy) return;
    state.fields = extractFields();
    const empty = state.fields.filter((f) => isEmpty(f));
    const pending = empty.filter((f) => state.status.get(f.key)?.status !== "sensitive");
    if (!pending.length) { state.msg = empty.length ? "Só faltam perguntas sensíveis (salário, visto…): essas ficam para você." : "Tudo já está preenchido."; return render(); }
    state.busy = true;
    render(`A IA está escrevendo ${pending.length} resposta(s)… (pode levar até 1 minuto)`);
    try {
      const { filled } = await fillFields(pending, true);
      state.msg = filled ? `✨ ${filled} resposta(s) escritas pela IA (contorno azul). Leia e ajuste se precisar.` : "A IA não encontrou o que responder nos campos restantes.";
    } catch (e) { state.msg = `A IA falhou: ${e.message}`; }
    state.busy = false;
    render();
  }

  // ---------------- painel (shadow DOM, visual do app) ----------------
  let host, shadow;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const ICON = {
    spark: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2z"/></svg>',
    min: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/></svg>',
    check: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6 9 17l-5-5"/></svg>',
  };
  const CSS_TEXT = `
    :host{all:initial}
    *{box-sizing:border-box}
    .root{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Inter",system-ui,"Segoe UI",sans-serif;font-size:13px;line-height:1.45;color:#0f172a;letter-spacing:-.01em}
    .fab{display:flex;align-items:center;gap:8px;border:0;cursor:pointer;background:linear-gradient(135deg,#2563eb,#0ea5e9);color:#fff;border-radius:999px;padding:10px 14px;box-shadow:0 8px 24px rgba(37,99,235,.35);font:600 13px/1 inherit;font-family:inherit}
    .fab .n{background:#fff;color:#2563eb;border-radius:999px;padding:2px 7px;font-size:11px}
    .card{width:340px;max-height:78vh;display:flex;flex-direction:column;background:#fff;border:1px solid #e3e7ef;border-radius:16px;box-shadow:0 2px 4px rgba(15,23,42,.06),0 18px 40px -12px rgba(15,23,42,.28);overflow:hidden}
    .hd{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid #eef1f6}
    .brand{display:grid;place-items:center;width:26px;height:26px;border-radius:8px;background:linear-gradient(135deg,#2563eb,#0ea5e9);color:#fff}
    .ttl{font-weight:600;flex:1}
    .ib{border:0;background:transparent;color:#64748b;cursor:pointer;border-radius:8px;width:28px;height:28px;display:grid;place-items:center}
    .ib:hover{background:#eef1f6;color:#0f172a}
    .bd{padding:12px;overflow:auto;display:flex;flex-direction:column;gap:12px}
    .job{display:flex;gap:10px;align-items:flex-start}
    .logo{width:40px;height:40px;border-radius:10px;border:1px solid #e3e7ef;background:#fff;display:grid;place-items:center;overflow:hidden;flex-shrink:0;font-weight:600;color:#fff}
    .logo img{width:100%;height:100%;object-fit:contain;padding:4px}
    .jt{font-weight:600;font-size:14px;line-height:1.3}
    .muted{color:#526075;font-size:12px}
    .pill{display:inline-flex;align-items:center;gap:4px;border-radius:999px;padding:2px 8px;font-size:11px;font-weight:600}
    .p-top{background:#05966920;color:#047857}.p-bet{background:#eaf2ff;color:#2563eb}.p-volume{background:#d9770620;color:#b45309}.p-discard,.p-blocked{background:#eef1f6;color:#526075}
    .bars{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .bar{font-size:11px;color:#526075}.bar b{color:#0f172a}
    .track{height:6px;border-radius:99px;background:#eef1f6;margin-top:3px;overflow:hidden}.track i{display:block;height:100%;border-radius:99px}
    .sec{border:1px solid #eef1f6;border-radius:12px;padding:10px}
    .sec h4{margin:0 0 6px;font-size:12px;font-weight:600;color:#0f172a}
    .prog{height:6px;border-radius:99px;background:#eef1f6;overflow:hidden;margin:6px 0}.prog i{display:block;height:100%;background:linear-gradient(90deg,#2563eb,#0ea5e9);transition:width .4s}
    .list{display:flex;flex-direction:column;gap:4px;margin-top:6px;max-height:180px;overflow:auto}
    .it{display:flex;align-items:center;gap:6px;border:0;background:#f8fafc;border-radius:8px;padding:6px 8px;text-align:left;cursor:pointer;font:inherit;color:inherit}
    .it:hover{background:#eaf2ff}
    .it span{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .chip{font-size:10px;font-weight:600;border-radius:999px;padding:1px 6px;white-space:nowrap}
    .c-empty{background:#d9770620;color:#b45309}.c-suggestion{background:#eaf2ff;color:#2563eb}.c-sensitive{background:#dc262618;color:#b91c1c}.c-ai{background:#eaf2ff;color:#2563eb}
    .btns{display:flex;gap:6px;flex-wrap:wrap}
    .b{border:0;border-radius:10px;padding:8px 12px;font:600 12px/1 inherit;font-family:inherit;cursor:pointer;display:inline-flex;align-items:center;gap:6px;transition:transform .1s,background .15s}
    .b:active{transform:scale(.97)}
    .b1{background:#2563eb;color:#fff;box-shadow:0 2px 8px rgba(37,99,235,.3)}.b1:hover{background:#1d4ed8}
    .b2{background:#eef1f6;color:#0f172a}.b2:hover{background:#e3e7ef}
    .b[disabled]{opacity:.55;cursor:wait}
    .grow{flex:1;justify-content:center}
    .msg{font-size:12px;color:#334155;background:#f8fafc;border-radius:10px;padding:8px 10px}
    .ok{color:#047857}.bad{color:#b91c1c}
    .spin{width:12px;height:12px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:s .7s linear infinite}
    @keyframes s{to{transform:rotate(360deg)}}
    @media (prefers-color-scheme:dark){
      .root{color:#e5e9f2}.card{background:#11151f;border-color:#232a3b}.hd,.sec{border-color:#232a3b}.muted,.bar{color:#a3adc2}.bar b{color:#e5e9f2}
      .track,.prog{background:#1a2030}.it,.msg{background:#1a2030;color:#e5e9f2}.it:hover{background:#172554}.b2{background:#1a2030;color:#e5e9f2}.ib:hover{background:#1a2030;color:#e5e9f2}
      .sec h4{color:#e5e9f2}.logo{border-color:#232a3b}
    }`;
  function ensureHost() {
    if (host) return;
    host = document.createElement("div");
    host.id = "tracker-assistant";
    host.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483646";
    shadow = host.attachShadow({ mode: "open" });
    document.documentElement.appendChild(host);
    try {
      const pos = JSON.parse(localStorage.getItem("trackerAssistantPos") || "null");
      if (pos?.left && pos?.top) Object.assign(host.style, { left: pos.left, top: pos.top, right: "auto", bottom: "auto" });
    } catch {}
    state.minimized = session.get().minimized === true;
  }
  const QUAD = { top: "Prioridade máxima", bet: "Aposta", volume: "Volume", discard: "Descartar", blocked: "Bloqueada" };
  const scoreColor = (v) => (v >= 60 ? "#16a34a" : v >= 40 ? "#d97706" : "#dc2626");
  const initials = (n) => (n || "?").split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

  function render(busyMsg) {
    if (!IS_TOP && !state.fields.length) return;
    ensureHost();
    const c = state.card;
    const fieldsTotal = state.fields.length;
    const pending = state.fields.filter((f) => isEmpty(f)).map((f) => ({ f, s: state.status.get(f.key) || { status: "empty" } }));
    if (state.minimized) {
      shadow.innerHTML = `<style>${CSS_TEXT}</style><div class="root"><button class="fab" id="open">${ICON.spark} Assistente${pending.length ? ` <span class="n">${pending.length}</span>` : ""}</button></div>`;
      shadow.getElementById("open").onclick = () => { state.minimized = false; session.set({ minimized: false }); render(); };
      return;
    }
    let body = "";
    if (c?.known) {
      const s = c.score;
      const logo = state.logo ? `<img src="${state.logo}" alt="">` : `<span style="background:linear-gradient(135deg,#2563eb,#0ea5e9);width:100%;height:100%;display:grid;place-items:center">${esc(initials(c.company))}</span>`;
      body += `<div class="job"><div class="logo">${logo}</div><div style="flex:1;min-width:0"><div class="jt">${esc(c.title)}</div><div class="muted">${esc(c.company)}${c.location ? ` · ${esc(c.location)}` : ""}</div>
        ${s ? `<div style="margin-top:4px"><span class="pill p-${esc(s.quadrant)}">${esc(QUAD[s.quadrant] || s.quadrant)} · ${Math.round(s.chance * 0.5 + s.attractiveness * 0.5)}</span></div>` : ""}</div></div>`;
      if (s) body += `<div class="bars"><div class="bar">Chance <b>${Math.round(s.chance)}</b><div class="track"><i style="width:${s.chance}%;background:${scoreColor(s.chance)}"></i></div></div>
        <div class="bar">Atratividade <b>${Math.round(s.attractiveness)}</b><div class="track"><i style="width:${s.attractiveness}%;background:${scoreColor(s.attractiveness)}"></i></div></div></div>`;
      const extra = [];
      if (c.responsiveness?.rate != null) extra.push(`Costuma responder ~${Math.round(c.responsiveness.rate * 100)}%`);
      if (c.reputation?.rating) extra.push(`Reputação ${Number(c.reputation.rating).toFixed(1)}`);
      if (c.reputation?.layoffs) extra.push('<span class="bad">layoff recente</span>');
      if (extra.length) body += `<div class="muted">${extra.join(" · ")}</div>`;
      if (s?.missing_must?.length) body += `<div class="muted">Você não tem: ${esc(s.missing_must.slice(0, 4).join(", "))}</div>`;
      if (c.application?.submitted_at) body += `<div class="msg ok">${ICON.check} Você já se candidatou a esta vaga.</div>`;
    } else if (state.linkedinList.length) {
      body += `<div class="sec"><h4>${state.linkedinList.length} vaga(s) nesta busca do LinkedIn</h4><div class="muted">Envie para a aba Vagas do tracker: elas recebem nota e você se candidata com o assistente.</div>
        <div class="btns" style="margin-top:8px"><button class="b b1 grow" id="import">Importar para o tracker</button></div></div>`;
    } else if (state.pageInfo?.looks_like_job) {
      body += `<div class="sec"><h4>Vaga nova</h4><div class="muted">Ainda não está no seu tracker.</div><div class="btns" style="margin-top:8px"><button class="b b1 grow" id="an">Avaliar e salvar vaga</button></div></div>`;
    }
    if (fieldsTotal) {
      body += `<div class="sec"><h4>Formulário · ${fieldsTotal - pending.length} de ${fieldsTotal} preenchidos</h4><div class="prog"><i style="width:${Math.max(4, Math.round(((fieldsTotal - pending.length) / fieldsTotal) * 100))}%"></i></div>`;
      if (pending.length) {
        body += `<div class="muted">Faltam (clique para ir ao campo):</div><div class="list">${pending.slice(0, 12).map(({ f, s }) =>
          `<button class="it" data-go="${esc(f.key)}"><span>${esc(f.label)}</span><em class="chip c-${s.status}">${{ empty: "você responde", suggestion: "tem sugestão", sensitive: "sensível", ai: "IA" }[s.status] || "falta"}</em></button>`).join("")}</div>`;
      } else body += `<div class="muted ok">Tudo preenchido. Revise e clique em enviar no site.</div>`;
      body += `<div class="btns" style="margin-top:8px"><button class="b b1 grow" id="ai" ${state.busy ? "disabled" : ""}>${state.busy ? '<i class="spin"></i>' : ICON.spark} Completar com IA</button><button class="b b2" id="refill" ${state.busy ? "disabled" : ""}>Preencher de novo</button></div></div>`;
    }
    const msg = busyMsg || state.msg;
    if (msg) body += `<div class="msg">${esc(msg)}</div>`;
    body += `<div class="btns"><button class="b b2 grow" id="sent">${ICON.check} Já me candidatei</button>${c?.known ? '<button class="b b2" id="openapp">Abrir no tracker</button>' : ""}</div>`;
    shadow.innerHTML = `<style>${CSS_TEXT}</style><div class="root"><div class="card"><div class="hd"><span class="brand">${ICON.spark}</span><span class="ttl" title="Arraste para mover">Assistente de candidatura</span><button class="ib" id="min" title="Minimizar">${ICON.min}</button></div><div class="bd">${body}</div></div></div>`;
    const $ = (id) => shadow.getElementById(id);
    $("min").onclick = () => { state.minimized = true; session.set({ minimized: true }); render(); };
    const hd = shadow.querySelector(".hd");
    hd.style.cursor = "grab";
    hd.onmousedown = (ev) => {
      if (ev.target.closest("button")) return;
      ev.preventDefault();
      const r = host.getBoundingClientRect();
      const dx = ev.clientX - r.left, dy = ev.clientY - r.top;
      const move = (m) => {
        host.style.left = `${Math.max(4, Math.min(innerWidth - r.width - 4, m.clientX - dx))}px`;
        host.style.top = `${Math.max(4, Math.min(innerHeight - 60, m.clientY - dy))}px`;
        host.style.right = "auto"; host.style.bottom = "auto";
      };
      const up = () => {
        removeEventListener("mousemove", move, true); removeEventListener("mouseup", up, true);
        try { localStorage.setItem("trackerAssistantPos", JSON.stringify({ left: host.style.left, top: host.style.top })); } catch {}
      };
      addEventListener("mousemove", move, true); addEventListener("mouseup", up, true);
    };
    $("an")?.addEventListener("click", analyze);
    $("import")?.addEventListener("click", importLinkedin);
    $("ai")?.addEventListener("click", aiFill);
    $("refill")?.addEventListener("click", () => { state.status.clear(); autoFill(false); });
    $("sent")?.addEventListener("click", () => reportSubmitted(true));
    $("openapp")?.addEventListener("click", () => window.open(`${(state.cfg.apiUrl || "").replace(":8000", ":3100")}/vagas/${c.job_id}`, "_blank"));
    shadow.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => {
      const key = b.getAttribute("data-go");
      const el = byKey(key) || radiosOf(key)[0];
      if (!el) return;
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      setTimeout(() => el.focus({ preventScroll: true }), 350);
    }));
  }
  function say(m) { state.msg = m; render(); }

  // ---------------- vaga: classificar, avaliar, logo ----------------
  const pageText = () => (document.body?.innerText || "").slice(0, 20000);
  function localLooksRelevant() {
    if (KNOWN_HOSTS.some((h) => location.href.includes(h))) return true;
    const hits = new Set((pageText().match(JOB_WORDS) || []).map((x) => x.toLowerCase())).size;
    return hits >= 2 || !!document.querySelector("input[type=file], input[type=email], input[autocomplete=email]");
  }
  async function loadLogo() {
    state.logo = null;
    if (!state.card?.company_id) return;
    try { state.logo = await bg({ type: "logo", companyId: state.card.company_id }); render(); } catch {}
  }
  async function classify() {
    const info = await api("POST", "/page", { url: location.href, title: document.title, text: pageText(), has_form: state.fields.length > 0, session_job_id: session.get().jobId || null });
    if (info.known) {
      state.card = info;
      session.set(info.flow_page ? { jobId: info.job_id } : { jobId: info.job_id, jobUrl: location.href, company: info.company, jobTitle: info.title });
      loadLogo();
      if (info.needs_details) analyze(true); // vaga importada sem descrição: completa com o texto desta página
    } else state.pageInfo = info;
    if (info.looks_like_job) session.set({ jobUrl: location.href, pageTitle: document.title });
    if (info.auto_analyze && !info.known) await analyze();
    if (info.success_page) await reportSubmitted(false);
  }
  async function analyze(silent) {
    try {
      if (!silent) say("Avaliando a vaga…");
      state.card = await api("POST", "/analyze", { url: location.href, title: document.title, text: pageText() });
      session.set({ jobId: state.card.job_id, jobUrl: location.href, company: state.card.company, jobTitle: state.card.title });
      state.msg = silent ? state.msg : "Vaga salva e avaliada.";
      loadLogo();
      render();
    } catch (e) { if (!silent) say(`Não foi possível avaliar: ${e.message}`); }
  }

  // ---------------- LinkedIn: importar as vagas da busca ----------------
  const isLinkedinSearch = () => /linkedin\.com\/jobs\/(search|collections)/.test(location.href);
  function scrapeLinkedin() {
    const out = new Map();
    document.querySelectorAll('a[href*="/jobs/view/"]').forEach((a) => {
      const m = a.href.match(/\/jobs\/view\/(\d+)/);
      if (!m || out.has(m[1])) return;
      const card = a.closest("li, .job-card-container, [data-job-id], [data-occludable-job-id]") || a.parentElement;
      const title = txt(a).split("\n")[0].replace(/\s+with verification$/i, "").trim();
      if (!title) return;
      const lines = (card?.innerText || "").split("\n").map((s) => s.trim()).filter((s) => s && s !== title);
      const company = txt(card?.querySelector(".artdeco-entity-lockup__subtitle, .job-card-container__primary-description, .job-card-container__company-name")) || lines[0] || "";
      const location_ = txt(card?.querySelector(".job-card-container__metadata-item, .artdeco-entity-lockup__caption")) || lines[1] || "";
      out.set(m[1], { external_id: m[1], title, company, location: location_, easy_apply: /easy apply|candidatura simplificada/i.test(card?.innerText || ""), text: (card?.innerText || "").slice(0, 1500) });
    });
    return [...out.values()];
  }
  async function importLinkedin() {
    const jobs = scrapeLinkedin();
    if (!jobs.length) return say("Não encontrei vagas na lista. Role a lista para carregar e tente de novo.");
    say(`Importando ${jobs.length} vaga(s)…`);
    try {
      const r = await api("POST", "/import-list", { source: "linkedin", jobs });
      say(`✓ ${r.created} nova(s) e ${r.existing} já conhecida(s). Elas aparecem em Vagas com nota em instantes. Role a lista para ver mais e importe de novo.`);
    } catch (e) { say(`Erro ao importar: ${e.message}`); }
  }

  // ---------------- sugestão ao clicar num campo ----------------
  let bubble, hideTimer;
  const cache = new Map();
  function hideBubble() { bubble?.remove(); bubble = null; }
  function bubbleBox() {
    const box = document.createElement("div");
    box.style.cssText = "position:fixed;z-index:2147483647;max-width:380px;font:13px/1.4 -apple-system,BlinkMacSystemFont,Inter,'Segoe UI',sans-serif;background:#0f172a;color:#fff;padding:8px 10px;border-radius:12px;box-shadow:0 10px 30px rgba(2,6,23,.35);display:flex;align-items:center;gap:8px;flex-wrap:wrap";
    return box;
  }
  const bubbleBtn = (label, primary) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.style.cssText = `border:0;border-radius:8px;padding:5px 10px;cursor:pointer;font:600 12px/1 inherit;font-family:inherit;${primary ? "background:#2563eb;color:#fff" : "background:rgba(255,255,255,.12);color:#fff"}`;
    return b;
  };
  /** O painel nunca cobre o campo em que você está: troca de lado quando houver sobreposição. */
  function dodge(el) {
    if (!host) return;
    const a = host.getBoundingClientRect(), b = el.getBoundingClientRect();
    const overlap = !(b.right < a.left || b.left > a.right || b.bottom < a.top || b.top > a.bottom);
    if (!overlap) return;
    const onRight = host.style.left === "" || host.style.left === "auto";
    host.style.transition = "opacity .15s";
    host.style.opacity = "0";
    setTimeout(() => {
      if (onRight) { host.style.left = "16px"; host.style.right = "auto"; } else { host.style.right = "16px"; host.style.left = "auto"; }
      host.style.opacity = "1";
    }, 150);
  }
  async function onFocus(e) {
    if (state.filling) return;
    clearTimeout(hideTimer);
    const el = e.target;
    if (!(el instanceof HTMLElement) || !el.matches("input, select, textarea") || el.closest("#tracker-assistant")) return;
    dodge(el);
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (["hidden", "password", "file", "submit", "button", "checkbox", "radio"].includes(type) || SKIP.test(`${el.name || ""} ${el.id || ""}`)) return;
    if (el.value && el.tagName !== "SELECT") return;
    if (!el.dataset.trk) el.dataset.trk = newKey();
    const field = extractFields().find((f) => f.key === el.dataset.trk);
    if (!field) return;
    const show = (s, aiTried) => {
      if (document.activeElement !== el) return;
      hideBubble();
      const r = el.getBoundingClientRect();
      bubble = bubbleBox();
      bubble.style.left = `${Math.max(8, Math.min(r.left, innerWidth - 390))}px`;
      bubble.style.top = `${r.bottom + 6 + 60 > innerHeight ? r.top - 52 : r.bottom + 6}px`;
      const val = s?.value;
      const label = document.createElement("span");
      label.style.cssText = "flex:1;min-width:0";
      label.innerHTML = val ? `💡 <b>${esc(String(val)).slice(0, 220)}</b>` : s?.sensitive ? "🔒 Pergunta sensível: responda você" : "Sem resposta salva para esta pergunta.";
      bubble.appendChild(label);
      if (val) {
        const use = bubbleBtn("Usar", true);
        use.onmousedown = async (ev) => {
          ev.preventDefault();
          state.filling = true;
          const ok = await setValue(field, val).finally(() => { state.filling = false; });
          state.status.set(field.key, { label: field.label, status: ok ? "filled" : "empty", value: val, source: s.source || "sugestão" });
          if (ok) paint(field.kind === "radio" ? radiosOf(field.key)[0] : el, "ok");
          hideBubble();
          render();
        };
        bubble.appendChild(use);
      }
      if (!aiTried && !s?.sensitive && ["text", "textarea", "typeahead"].includes(field.kind)) {
        const ai = bubbleBtn(val ? "✨ Outra com IA" : "✨ Gerar com IA");
        ai.onmousedown = async (ev) => {
          ev.preventDefault();
          label.textContent = "✨ Escrevendo…";
          try { show(await api("POST", "/suggest", { url: location.href, job_id: jobId(), field, allow_ai: true }), true); } catch (er) { label.textContent = er.message; }
        };
        bubble.appendChild(ai);
      }
      document.documentElement.appendChild(bubble);
    };
    const known = state.status.get(field.key);
    if (known?.value && known.status === "suggestion") return show({ value: known.value, source: "sugestão" }, false);
    const ck = `${field.label}|${field.options.join(";")}`;
    try {
      const s = cache.get(ck) ?? (await api("POST", "/suggest", { url: location.href, job_id: jobId(), field, allow_ai: false }));
      cache.set(ck, s);
      show(s, false);
    } catch {}
  }

  // ---------------- aprendizado: o que você digitou/escolheu ----------------
  function onChange(e) {
    const el = e.target;
    if (!(el instanceof HTMLElement) || !el.matches("input, select, textarea") || el.closest("#tracker-assistant")) return;
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (["password", "hidden", "file"].includes(type) || SKIP.test(`${el.name || ""} ${el.id || ""}`)) return;
    let label, value, kind = "text", options = [];
    if (type === "radio") { label = groupQuestion(el); value = radioOptionLabel(el); kind = "radio"; }
    else {
      label = labelFor(el); kind = kindOf(el);
      value = kind === "checkbox" ? el.checked : el.tagName === "SELECT" ? el.options[el.selectedIndex]?.text?.trim() : el.value;
      if (el.tagName === "SELECT") options = [...el.options].map((o) => o.text.trim()).filter(Boolean);
    }
    if (label && value !== null && value !== "" && value !== undefined) {
      state.edits.set(label, { question: label, value, field_kind: kind, options });
      session.set({ answers: [...state.edits.values()] });
    }
    if (el.dataset.trk && state.status.has(el.dataset.trk)) {
      const st = state.status.get(el.dataset.trk);
      if (st.status !== "filled" && st.status !== "ai") state.status.set(el.dataset.trk, { ...st, status: "filled", source: "você" });
      clearTimeout(renderTimer); renderTimer = setTimeout(() => render(), 300);
    }
  }
  let renderTimer;

  // ---------------- detecção de envio ----------------
  async function reportSubmitted(manual) {
    if (state.reported) return;
    const s = session.get();
    if (!manual && !s.jobUrl && !state.card) return;
    state.reported = true;
    try {
      const res = await api("POST", "/submitted", {
        url: s.jobUrl || location.href, title: s.pageTitle || document.title, text: manual ? pageText() : "",
        job_id: jobId(), company: s.company || null, job_title: s.jobTitle || null,
        answers: s.answers || [...state.edits.values()],
      });
      session.set({ answers: [], submittedAppId: res.application_id, minimized: false });
      state.minimized = false; // confirmação importante: o painel abre para mostrar
      say(res.already ? "Esta candidatura já estava no seu acompanhamento." : "✓ Candidatura adicionada ao seu acompanhamento.");
    } catch (e) { state.reported = false; say(`Erro ao registrar: ${e.message}`); }
  }

  // ---------------- observação da página ----------------
  let scanTimer;
  function watch() {
    new MutationObserver(() => {
      clearTimeout(scanTimer);
      scanTimer = setTimeout(() => {
        const s = session.get();
        if ((s.formSubmitted || state.edits.size || state.status.size || state.card) && SUCCESS.test(pageText())) { reportSubmitted(false); return; }
        if (isLinkedinSearch()) { const n = scrapeLinkedin().length; if (n !== state.linkedinList.length) { state.linkedinList = scrapeLinkedin(); render(); } }
        // formulários em etapas: campos novos são preenchidos assim que aparecem
        const fresh = extractFields().filter((f) => !state.status.has(f.key));
        if (fresh.length && state.cfg?.autoFill !== false && (state.card || state.status.size || localLooksRelevant())) autoFill(true);
      }, 900);
    }).observe(document.documentElement, { childList: true, subtree: true });
    document.addEventListener("submit", () => session.set({ formSubmitted: Date.now(), answers: [...state.edits.values()] }), true);
  }

  // ---------------- início ----------------
  let wired = false;
  async function start() {
    state.cfg = await bg({ type: "config" }).catch(() => null);
    if (!state.cfg?.enabled || !state.cfg.token) return;
    if ((state.cfg.ignoredDomains || []).some((d) => location.host.includes(d))) return;
    if (IS_TOP && isLinkedinSearch()) {
      const discovery = await bg({ type: "linkedinDiscoveryInfo" }).catch(() => null);
      if (discovery && !linkedinDiscoveryRunning) {
        linkedinDiscoveryRunning = true;
        let jobs = [];
        for (let attempt = 0; attempt < 30 && !jobs.length; attempt++) {
          jobs = scrapeLinkedin();
          if (!jobs.length) await new Promise((resolve) => setTimeout(resolve, 1000));
        }
        try {
          if (!jobs.length) throw new Error("nenhuma vaga visível; verifique se a sessão do LinkedIn está conectada");
          const imported = await api("POST", "/import-list", { source: "linkedin", jobs });
          await bg({
            type: "linkedinDiscoveryComplete",
            count: jobs.length,
            created: imported.created,
            existing: imported.existing,
          });
        } catch (error) {
          await bg({ type: "linkedinDiscoveryComplete", error: error.message });
        }
        return;
      }
    }
    if (!wired) {
      wired = true;
      document.addEventListener("focusin", onFocus, true);
      document.addEventListener("mousemove", (ev) => {
        const t = ev.target;
        if (!state.filling && t instanceof HTMLElement && t.matches?.("input, select, textarea") && !t.closest("#tracker-assistant")) dodge(t);
      }, { capture: true, passive: true });
      document.addEventListener("focusout", () => { clearTimeout(hideTimer); hideTimer = setTimeout(hideBubble, 200); }, true);
      document.addEventListener("change", onChange, true);
      watch();
    }
    if (SUCCESS.test(pageText()) && session.get().jobUrl) { await reportSubmitted(false); return; }
    state.fields = extractFields();
    if (isLinkedinSearch()) state.linkedinList = scrapeLinkedin();
    const relevant = localLooksRelevant() || state.fields.some((f) => f.kind === "file" || /e-?mail|curr[ií]culo|resume|cv/i.test(f.label));
    if (!relevant && !state.linkedinList.length) return;
    if (!IS_TOP && !state.fields.length) return;
    try { await classify(); } catch { state.pageInfo = { looks_like_job: false }; }
    if (state.card || state.pageInfo?.looks_like_job || state.fields.length || state.linkedinList.length) render();
    if (state.fields.length && state.cfg.autoFill !== false) autoFill(false);
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "tracker:show-panel") { state.minimized = false; session.set({ minimized: false }); state.fields = extractFields(); classify().catch(() => {}).finally(() => render()); }
    if (msg.type === "tracker:fill") { state.status.clear(); autoFill(false); }
    if (msg.type === "tracker:ai") aiFill();
  });

  // SPAs (LinkedIn etc.) mudam de URL sem recarregar
  let lastUrl = location.href;
  setInterval(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      state.card = null; state.pageInfo = null; state.reported = false; state.status.clear(); state.msg = ""; state.logo = null; state.linkedinList = [];
      setTimeout(start, 1200);
    }
  }, 1000);

  setTimeout(start, 1000);
})();
