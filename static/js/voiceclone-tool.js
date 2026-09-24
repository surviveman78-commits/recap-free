(() => {
  const openBtn = document.getElementById("openVoiceCloneBtn");
  const closeBtn = document.getElementById("closeVoiceCloneBtn");
  const modal = document.getElementById("voiceCloneModal");
  const fileInput = document.getElementById("voiceCloneFile");
  const fileName = document.getElementById("voiceCloneFileName");
  const refText = document.getElementById("voiceCloneRefText");
  const script = document.getElementById("voiceCloneScript");
  const count = document.getElementById("voiceCloneCount");
  const status = document.getElementById("voiceCloneDemoStatus");
  const previewBtn = document.getElementById("voiceClonePreviewBtn");
  const generateBtn = document.getElementById("voiceCloneGenerateBtn");
  const output = document.getElementById("voiceCloneOutput");
  const audio = document.getElementById("voiceCloneAudio");
  const download = document.getElementById("voiceCloneDownload");
  const history = document.getElementById("voiceCloneHistory");
  const toolHub = document.getElementById("toolHub");
  const recapPanel = document.getElementById("recapToolPanel");
  const openRecapBtn = document.getElementById("openRecapToolBtn");
  const recapCard = document.getElementById("recapToolCard");
  const backToToolsBtn = document.getElementById("backToToolsBtn");
  const moreToolsSection = document.getElementById("moreToolsSection");
  const settingsBtn = document.getElementById("openSettingsBtn");
  const headerHistoryBtn = document.getElementById("historyBtn");
  const ACTIVE_TOOL_KEY = "recap_testing_active_tool";

  const setSettingsVisible = (visible) => {
    if (settingsBtn) settingsBtn.style.display = visible ? "inline-flex" : "none";
  };
  if (headerHistoryBtn) headerHistoryBtn.style.display = "none";

  const showRecap = () => {
    if (!toolHub || !recapPanel) return;
    toolHub.style.display = "none";
    if (moreToolsSection) moreToolsSection.style.display = "none";
    recapPanel.style.display = "block";
    setSettingsVisible(true);
    localStorage.setItem(ACTIVE_TOOL_KEY, "recap");
    window.scrollTo(0, 0);
  };
  const showTools = () => {
    if (!toolHub || !recapPanel) return;
    recapPanel.style.display = "none";
    toolHub.style.display = "grid";
    if (moreToolsSection) moreToolsSection.style.display = "block";
    setSettingsVisible(false);
    localStorage.setItem(ACTIVE_TOOL_KEY, "dashboard");
    window.scrollTo(0, 0);
  };
  if (openRecapBtn) openRecapBtn.addEventListener("click", showRecap);
  if (recapCard) recapCard.addEventListener("click", (event) => { if (event.target !== openRecapBtn && !openRecapBtn?.contains(event.target)) showRecap(); });
  if (backToToolsBtn) backToToolsBtn.addEventListener("click", showTools);

  if (!openBtn || !modal) return;
  const open = () => { modal.classList.add("active"); loadHistory(); };
  const close = () => modal.classList.remove("active");
  const showVoice = () => {
    if (toolHub) toolHub.style.display = "grid";
    if (recapPanel) recapPanel.style.display = "none";
    if (moreToolsSection) moreToolsSection.style.display = "block";
    setSettingsVisible(false);
    localStorage.setItem(ACTIVE_TOOL_KEY, "voice");
    open();
  };
  openBtn.addEventListener("click", showVoice);
  closeBtn.addEventListener("click", close);
  modal.addEventListener("click", (event) => { if (event.target === modal) { close(); localStorage.setItem(ACTIVE_TOOL_KEY, "dashboard"); } });

  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files[0]) fileName.textContent = fileInput.files[0].name;
  });
  const updateCount = () => {
    const chars = script.value.length;
    count.textContent = `${chars.toLocaleString()} characters • ${Math.max(0, Math.round(chars / 7.2 / 60))} min estimated`;
  };
  updateCount();
  script.addEventListener("input", updateCount);
  const setStatus = (message, error = false) => {
    status.textContent = message;
    status.style.color = error ? "#dc2626" : "var(--primary)";
    status.style.display = "block";
  };

  function renderHistory(jobs) {
    if (!jobs.length) { history.innerHTML = `<p class="bv-empty-state">Voice Clone History မရှိသေးပါ</p>`; return; }
    history.innerHTML = jobs.map((job) => {
      const state = job.status === "completed" ? "✅" : job.status === "failed" ? "❌" : "⏳";
      const action = job.status === "completed" ? `<a class="bv-history-action-btn" href="/api/voiceclone/jobs/${job.job_id}/file" download="voice_clone_${job.job_id}.wav">⬇ WAV</a>` : "";
      const error = job.status === "failed" ? `<small>${(job.error || "Failed").slice(0, 80)}</small>` : `<small>${job.stage || job.status} • ${Math.round(job.progress || 0)}%</small>`;
      return `<div class="bv-history-item"><div class="bv-history-item-icon ${job.status === "completed" ? "completed" : job.status === "failed" ? "failed" : "running"}">${state}</div><div class="bv-history-item-body"><div class="bv-history-item-title">${job.reference_name || "Reference voice"}</div><div class="bv-history-item-meta">${job.script_chars || 0} characters • ${new Date((job.created_at || 0) * 1000).toLocaleString()}</div>${error}</div><div class="bv-history-item-actions">${action}</div></div>`;
    }).join("");
  }
  async function loadHistory() {
    try { const res = await fetch("/api/voiceclone/jobs", { cache: "no-store" }); const data = await res.json(); renderHistory(data.jobs || []); }
    catch (err) { setStatus(`History မဖတ်နိုင်ပါ: ${err.message}`, true); }
  }
  async function waitForJob(jobId) {
    for (;;) {
      const res = await fetch(`/api/voiceclone/jobs/${jobId}`, { cache: "no-store" });
      const job = await res.json();
      setStatus(`${job.stage || job.status} • ${Math.round(job.progress || 0)}%`);
      if (job.status === "completed") {
        const url = `/api/voiceclone/jobs/${jobId}/file`;
        audio.src = url; download.href = url; download.download = `voice_clone_${jobId}.wav`; output.style.display = "flex"; generateBtn.disabled = false; previewBtn.disabled = false; await loadHistory(); return;
      }
      if (job.status === "failed") { generateBtn.disabled = false; previewBtn.disabled = false; setStatus(`မအောင်မြင်ပါ: ${job.error || "Voice Clone failed"}`, true); await loadHistory(); return; }
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
  }
  async function submitJob(preview) {
    const file = fileInput.files && fileInput.files[0];
    if (!file) { setStatus("Reference voice audio ကို အရင်ရွေးပါ။", true); return; }
    if (!refText.value.trim()) { setStatus("Reference Text ထည့်ပါ။", true); refText.focus(); return; }
    const text = preview ? script.value.slice(0, 320) : script.value;
    if (!text.trim()) { setStatus("ပြောစေချင်တဲ့စာသား ထည့်ပါ။", true); return; }
    const form = new FormData(); form.append("reference_audio", file); form.append("reference_text", refText.value.trim()); form.append("script", text);
    generateBtn.disabled = true; previewBtn.disabled = true; output.style.display = "none"; setStatus(preview ? "Preview Voice Clone စတင်နေပါသည်..." : "Long-form Voice Clone စတင်နေပါသည်...");
    try { const res = await fetch("/api/voiceclone/jobs", { method: "POST", body: form }); const data = await res.json(); if (!res.ok) throw new Error(data.detail || "Voice Clone request failed"); await loadHistory(); await waitForJob(data.job_id); }
    catch (err) { generateBtn.disabled = false; previewBtn.disabled = false; setStatus(`Error: ${err.message}`, true); }
  }
  previewBtn.addEventListener("click", () => submitJob(true));
  generateBtn.addEventListener("click", () => submitJob(false));

  setSettingsVisible(false);
  const savedTool = localStorage.getItem(ACTIVE_TOOL_KEY);
  if (savedTool === "recap") showRecap(); else if (savedTool === "voice") showVoice(); else showTools();
})();
