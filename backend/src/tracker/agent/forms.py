"""Extração e preenchimento genéricos de formulários pelo DOM (rótulos acessíveis, não classes CSS)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.async_api import Locator, Page

from tracker.agent.human import Pace

EXTRACT_JS = r"""
(root) => {
  root = root || document;
  const doc = root.ownerDocument || document;
  const fields = [];
  let i = 0;
  // chaves únicas por extração; limpa marcações de etapas anteriores
  doc.querySelectorAll('[data-tracker-key],[data-tracker-group]').forEach(e => {
    e.removeAttribute('data-tracker-key'); e.removeAttribute('data-tracker-group'); e.removeAttribute('data-tracker-idx'); });
  const prefix = 'tk' + Date.now().toString(36) + '_';
  const txt = (el) => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const visible = (el) => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const labelFor = (el) => {
    const aria = el.getAttribute('aria-label'); if (aria) return aria.trim();
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(/\s+/).map(id => txt(doc.getElementById(id))).join(' ').trim(); if (t) return t; }
    if (el.id) { const l = root.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return txt(l); }
    const wrap = el.closest('label'); if (wrap) return txt(wrap);
    const fs = el.closest('fieldset'); const lg = fs?.querySelector('legend'); if (lg) return txt(lg);
    return el.getAttribute('placeholder') || el.name || '';
  };
  const errorFor = (el) => {
    if (el.getAttribute('aria-invalid') !== 'true') return null;
    const d = el.getAttribute('aria-describedby');
    return (d && txt(doc.getElementById(d))) || 'inválido';
  };
  const seen = new Set();
  root.querySelectorAll('input, select, textarea').forEach(el => {
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (type === 'hidden' || type === 'submit' || type === 'button' || el.disabled) return;
    if (type === 'file' ? !(visible(el) || visible(el.closest('label, div, section, form'))) : !visible(el)) return;
    if (type === 'radio') {
      const name = el.name || el.id; if (seen.has(name)) return; seen.add(name);
      const group = Array.from(root.querySelectorAll(`input[type=radio][name="${CSS.escape(name)}"]`));
      const key = prefix + (i++);
      group.forEach((r, idx) => { r.setAttribute('data-tracker-group', key); r.setAttribute('data-tracker-idx', idx); });
      const opts = group.map(r => { const l = r.id ? root.querySelector(`label[for="${CSS.escape(r.id)}"]`) : r.closest('label'); return txt(l) || r.value; });
      const fs = el.closest('fieldset');
      const checked = group.find(r => r.checked);
      fields.push({key, label: txt(fs?.querySelector('legend')) || labelFor(el), kind: 'radio', options: opts,
        required: group.some(r => r.required || r.getAttribute('aria-required') === 'true') || fs?.getAttribute('aria-required') === 'true',
        current_value: checked ? opts[group.indexOf(checked)] : null, error: null});
      return;
    }
    const key = prefix + (i++);
    el.setAttribute('data-tracker-key', key);
    let kind = el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea' : (type || 'text');
    if (el.getAttribute('role') === 'combobox' && el.tagName === 'INPUT') kind = 'typeahead';
    if (!['text','email','tel','number','date','file','checkbox','select','textarea','typeahead','url'].includes(kind)) kind = 'text';
    const options = el.tagName === 'SELECT'
      ? Array.from(el.options).filter(o => o.value && !/^(select an option|selecione|escolha)/i.test(o.text.trim())).map(o => o.text.trim())
      : [];
    let current = null;
    if (kind === 'checkbox') current = String(el.checked);
    else if (el.tagName === 'SELECT') current = el.value ? el.options[el.selectedIndex]?.text?.trim() : null;
    else if (kind !== 'file') current = el.value || null;
    fields.push({key, label: labelFor(el), kind: kind === 'url' ? 'text' : kind, options,
      required: el.required || el.getAttribute('aria-required') === 'true', current_value: current, error: errorFor(el)});
  });
  return fields;
}
"""


async def extract_fields(page: Page, container: Locator | None = None) -> list[dict[str, Any]]:
    if container is not None:
        return await container.evaluate(EXTRACT_JS)
    return await page.evaluate(EXTRACT_JS, None)


async def fill_fields(
    page: Page, fields: list[dict[str, Any]], values: dict[str, Any], pace: Pace, resume_path: Path | None
) -> list[str]:
    """Preenche os campos resolvidos. Retorna as chaves que não puderam ser preenchidas."""
    failed: list[str] = []
    by_key = {f["key"]: f for f in fields}
    for key, value in values.items():
        f = by_key.get(key)
        if f is None:
            continue
        try:
            if f["kind"] == "radio":
                idx = f["options"].index(value) if value in f["options"] else None
                if idx is None:
                    failed.append(key)
                    continue
                radio = page.locator(f'[data-tracker-group="{key}"][data-tracker-idx="{idx}"]')
                rid = await radio.get_attribute("id")
                target = page.locator(f'label[for="{rid}"]') if rid else radio
                if await target.count() == 0:
                    target = radio
                await pace.click(target.first)
                continue
            loc = page.locator(f'[data-tracker-key="{key}"]')
            if f["kind"] == "file":
                if value == "__resume__" and resume_path is not None:
                    await loc.set_input_files(str(resume_path))
                continue
            if f["kind"] == "select":
                await loc.select_option(label=str(value))
                await pace.pause(0.3, 1.0)
            elif f["kind"] == "checkbox":
                if isinstance(value, list):
                    continue
                await loc.set_checked(bool(value))
            elif f["kind"] == "typeahead":
                await pace.type(loc, str(value))
                option = page.get_by_role("option").first
                try:
                    await option.wait_for(timeout=3000)
                    await pace.click(option)
                except Exception:
                    await loc.press("Enter")
            else:
                if (f.get("current_value") or "") == str(value):
                    continue
                await pace.type(loc, str(value))
        except Exception:
            failed.append(key)
    return failed


async def click_button(page: Page, names: list[str], pace: Pace, scope: Locator | None = None) -> bool:
    """Clica no primeiro botão visível cujo nome acessível bate com algum dos textos."""
    import re

    root = scope or page
    for name in names:
        btn = root.get_by_role("button", name=re.compile(rf"^\s*{re.escape(name)}\b", re.I))
        if await btn.count() and await btn.first.is_visible():
            await pace.click(btn.first)
            return True
    return False


async def visible_button(page: Page, names: list[str], scope: Locator | None = None) -> bool:
    import re

    root = scope or page
    for name in names:
        btn = root.get_by_role("button", name=re.compile(rf"^\s*{re.escape(name)}\b", re.I))
        if await btn.count() and await btn.first.is_visible():
            return True
    return False
