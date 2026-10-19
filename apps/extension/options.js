const DEFAULTS = { apiUrl: "http://localhost:8000", token: "", enabled: true, ignoredDomains: ["mail.google.com", "web.whatsapp.com", "localhost:3100"] };
const $ = (id) => document.getElementById(id);
chrome.storage.sync.get(DEFAULTS).then((c) => {
  $("apiUrl").value = c.apiUrl; $("token").value = c.token; $("enabled").checked = c.enabled;
  $("ignored").value = (c.ignoredDomains || []).join("\n");
});
$("save").onclick = async () => {
  await chrome.storage.sync.set({
    apiUrl: $("apiUrl").value.trim() || DEFAULTS.apiUrl, token: $("token").value.trim(), enabled: $("enabled").checked,
    ignoredDomains: $("ignored").value.split("\n").map((s) => s.trim()).filter(Boolean),
  });
  $("status").textContent = "Salvo ✓";
};
