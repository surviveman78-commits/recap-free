(() => {
  const path = window.location.pathname;
  const isDashboard = path.endsWith("/") || path.endsWith("/index.html");
  const isRecapPage = path.endsWith("/recap.html");
  const isVoicePage = path.endsWith("/voiceclone.html");
  const go = (url) => { window.location.href = url; };
  const recapBtn = document.getElementById("openRecapToolBtn");
  const recapCard = document.getElementById("recapToolCard");
  const voiceBtn = document.getElementById("openVoiceCloneBtn");
  const voiceCard = document.getElementById("voiceCloneToolCard");
  const voiceTopDashboardBtn = document.getElementById("voiceCloneTopDashboardBtn");
  const toolHub = document.getElementById("toolHub");
  const moreTools = document.getElementById("moreToolsSection");
  const recapPanel = document.getElementById("recapToolPanel");
  const voiceModal = document.getElementById("voiceCloneModal");
  const settings = document.getElementById("openSettingsBtn");

  if (isDashboard) {
    localStorage.setItem("recap_testing_active_tool", "dashboard");
    if (toolHub) toolHub.style.display = "grid";
    if (moreTools) moreTools.style.display = "block";
    if (recapPanel) recapPanel.style.display = "none";
    if (voiceModal) voiceModal.classList.remove("active");
    if (settings) settings.style.display = "none";
    if (recapBtn) recapBtn.onclick = (event) => { event.stopPropagation(); go("/recap.html"); };
    if (recapCard) recapCard.onclick = () => go("/recap.html");
    if (voiceBtn) voiceBtn.onclick = (event) => { event.stopPropagation(); go("/voiceclone.html"); };
    if (voiceCard) voiceCard.onclick = () => go("/voiceclone.html");
    return;
  }

  const hero = document.querySelector(".bv-hero-section");

  if (isRecapPage) {
    localStorage.setItem("recap_testing_active_tool", "recap");
    document.body.classList.add("recap-page");
    if (toolHub) toolHub.style.display = "none";
    if (moreTools) moreTools.style.display = "none";
    if (recapPanel) recapPanel.style.display = "block";
    if (voiceModal) voiceModal.classList.remove("active");
    if (settings) settings.style.display = "inline-flex";
    const back = document.getElementById("backToToolsBtn");
    if (back) { back.textContent = "← Dashboard သို့ ပြန်သွားမည်"; back.onclick = () => go("/index.html"); }
  }

  if (isVoicePage) {
    localStorage.setItem("recap_testing_active_tool", "voice");
    document.body.classList.add("voiceclone-page");
    if (hero) hero.style.display = "none";
    if (toolHub) toolHub.style.display = "none";
    if (moreTools) moreTools.style.display = "none";
    if (recapPanel) recapPanel.style.display = "none";
    if (settings) settings.style.display = "none";
    if (voiceModal) voiceModal.classList.add("active", "voiceclone-page-active");
    if (voiceTopDashboardBtn) voiceTopDashboardBtn.onclick = () => go("/index.html");
    const close = document.getElementById("closeVoiceCloneBtn");
    if (close) { close.textContent = "← Dashboard"; close.title = "Dashboard သို့ ပြန်သွားမည်"; close.onclick = () => go("/index.html"); }
  }
})();
