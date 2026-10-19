const send = async (type) => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) chrome.tabs.sendMessage(tab.id, { type }).catch(() => {});
  window.close();
};
chrome.runtime.sendMessage({ type: "config" }, (r) => {
  const c = r?.data || {};
  document.getElementById("st").textContent = !c.token ? "Configure o token nas Opções." : c.enabled ? "Ativo · preenche sozinho ao abrir formulários" : "Desativado nas Opções";
});
document.getElementById("panel").onclick = () => send("tracker:show-panel");
document.getElementById("fill").onclick = () => send("tracker:fill");
document.getElementById("ai").onclick = () => send("tracker:ai");
document.getElementById("opts").onclick = () => chrome.runtime.openOptionsPage();
