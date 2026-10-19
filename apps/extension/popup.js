const send = async (type) => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) chrome.tabs.sendMessage(tab.id, { type }).catch(() => {});
  window.close();
};
chrome.runtime.sendMessage({ type: "config" }, (r) => {
  const c = r?.data || {};
  document.getElementById("st").textContent = !c.token ? "Configure o token nas opções." : c.enabled ? "Ativo" : "Desativado nas opções";
});
document.getElementById("panel").onclick = () => send("tracker:show-panel");
document.getElementById("fill").onclick = () => send("tracker:fill");
document.getElementById("opts").onclick = () => chrome.runtime.openOptionsPage();
