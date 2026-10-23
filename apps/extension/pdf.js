// Mostra o PDF do CV sob medida (a extensão busca com o token; a página do PDF nunca vê o token).
const id = location.hash.slice(1);
chrome.runtime.sendMessage({ type: "pdf", variantId: id }, (r) => {
  const m = document.getElementById("m");
  if (!r?.ok) { m.textContent = r?.error || "Não consegui abrir o PDF."; return; }
  const bytes = Uint8Array.from(atob(r.data), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
  const f = document.createElement("iframe");
  f.src = url;
  m.replaceWith(f);
});
