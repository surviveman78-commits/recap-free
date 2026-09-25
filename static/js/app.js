// AI Video Recap Studio - Client Controller (v3)
// Features: Refresh-proof job restore, Queue system, History, Subtitle toggle, Preview/SRT download

const BURMESE_STAGES = [
  "ဗီဒီယို ဒေါင်းလုဒ်လုပ်နေပါတယ်...",
  "အသံဖိုင် ထုတ်ယူနေပါတယ်...",
  "အသံကို စာသားအဖြစ် ပြောင်းနေပါတယ်...",
  "စာသားကို ဘာသာပြန် / ပြန်လည်ရေးသားနေပါတယ်...",
  "အသံဖိုင် ဖန်တီးနေပါတယ်...",
  "ဗီဒီယိုနဲ့ အသံ ပေါင်းနေပါတယ်...",
  "စာတန်းထိုးနေပါတယ်...",
  "ပြီးပါပြီ ✓"
];

let appSettings = {};
let voiceCatalog = { languages: [], voices_by_language: {} };
let systemFonts = [];
let fontFiles = {};
let targetLanguages = [];
const RESOLUTION_FONT_SIZES = { "1080p": 70, "tiktok1080": 70, "tiktok2k": 94, "2k": 94, "4k": 140 };
let currentEventSource = null;
let currentInputMode = "link";

// Active job tracking
let activeJobId = null;        // currently watched job in main view
let allJobs = {};              // all known job states { jobId: {...} }
let jobEventSources = {};      // SSE connections per job
let jobPollers = {};           // polling fallback for buffered SSE/proxy connections

// Drag state
let subPosX = 50.0;
let subPosY = 82.0;
let isDraggingSubtitle = false;

// ──────────────────────────────────────────────
// Theme Toggle
// ──────────────────────────────────────────────
const themeToggleBtn = document.getElementById("themeToggleBtn");
const themeIcon = document.getElementById("themeIcon");
const themeLabel = document.getElementById("themeLabel");

function applyTheme(theme) {
  if (theme === "dark") {
    document.documentElement.classList.add("dark");
    if (themeIcon) themeIcon.textContent = "☀️";
    if (themeLabel) themeLabel.textContent = "Light";
  } else {
    document.documentElement.classList.remove("dark");
    if (themeIcon) themeIcon.textContent = "🌙";
    if (themeLabel) themeLabel.textContent = "Dark";
  }
}

const savedTheme = localStorage.getItem("recap_theme") || "light";
applyTheme(savedTheme);

if (themeToggleBtn) {
  themeToggleBtn.addEventListener("click", () => {
    const isDark = document.documentElement.classList.contains("dark");
    const nextTheme = isDark ? "light" : "dark";
    localStorage.setItem("recap_theme", nextTheme);
    applyTheme(nextTheme);
  });
}

// ──────────────────────────────────────────────
// DOM References
// ──────────────────────────────────────────────
const openSettingsBtn = document.getElementById("openSettingsBtn");
const closeSettingsBtn = document.getElementById("closeSettingsBtn");
const cancelSettingsBtn = document.getElementById("cancelSettingsBtn");
const settingsModal = document.getElementById("settingsModal");
const settingsForm = document.getElementById("settingsForm");
const tabButtons = document.querySelectorAll(".bv-tab-btn, .tab-btn");
const tabContents = document.querySelectorAll(".bv-tab-content, .tab-content");

const groqApiKey = document.getElementById("groqApiKey");
const geminiApiKey = document.getElementById("geminiApiKey");
const outputResolution = document.getElementById("outputResolution");
const settingsTargetLang = document.getElementById("settingsTargetLang");
const aiMode = document.getElementById("aiMode");
const voiceEngine = document.getElementById("voiceEngine");
const edgeTtsSettingsBlock = document.getElementById("edgeTtsSettingsBlock");
const voxcpmSettingsBlock = document.getElementById("voxcpmSettingsBlock");
const edgeLanguageSelect = document.getElementById("edgeLanguageSelect");
const edgeVoiceSelect = document.getElementById("edgeVoiceSelect");
const voxcpmAudioFile = document.getElementById("voxcpmAudioFile");
const uploadRefAudioBtn = document.getElementById("uploadRefAudioBtn");
const currentRefAudioName = document.getElementById("currentRefAudioName");
const voxcpmRefText = document.getElementById("voxcpmRefText");

const fontStyleSelect = document.getElementById("fontStyleSelect");
const uploadCustomFontBtn = document.getElementById("uploadCustomFontBtn");
const customFontFileInput = document.getElementById("customFontFileInput");
const fontSizeRange = document.getElementById("fontSizeRange");
const fontSizeDisplay = document.getElementById("fontSizeDisplay");
const fontColorPicker = document.getElementById("fontColorPicker");
const fontColorHex = document.getElementById("fontColorHex");
const autoBlurSubtitlesToggle = document.getElementById("autoBlurSubtitlesToggle");
const autoBlurStatus = document.getElementById("autoBlurStatus");

const dragCanvasContainer = document.getElementById("dragCanvasContainer");
const draggableSubtitle = document.getElementById("draggableSubtitle");
const previewSubText = document.getElementById("previewSubText");
const fontLivePreview = document.getElementById("fontLivePreview");
const subtitleAnimationSelect = document.getElementById("subtitleAnimationSelect");
const posXLabel = document.getElementById("posXLabel");
const posYLabel = document.getElementById("posYLabel");
const resetPosBtn = document.getElementById("resetPosBtn");
const ratio916Btn = document.getElementById("ratio916Btn");
const ratio169Btn = document.getElementById("ratio169Btn");

function cleanUserStatusMessage(message) {
  const text = String(message || "");
  if (/h264_nvenc|libcuda\.so|Error while filtering|Nothing was written|FFmpeg/i.test(text)) {
    return "ဗီဒီယို rendering မအောင်မြင်ပါ။ GPU မရသဖြင့် CPU fallback ကို စမ်းပြီးပါပြီ။ Video format သို့မဟုတ် FFmpeg setup ကို စစ်ပါ။";
  }
  return text;
}

function applyAutoBlurUi(enabled) {
  const positionField = dragCanvasContainer ? dragCanvasContainer.closest(".bv-setting-field") : null;
  if (positionField) positionField.classList.toggle("auto-blur-locked", Boolean(enabled));
  if (autoBlurStatus) {
    autoBlurStatus.textContent = enabled
      ? "Auto Blur ဖွင့်ထားပါသည် — Gemini သတ်မှတ်သော band အလယ်မှာ စာတန်းကို fixed ထားပြီး drag ရွှေ့ခြင်း ပိတ်ထားပါသည်။"
      : "ပိတ်ထားပါက ပုံမှန် subtitle position ကိုသုံးပါမည်။"
  }
}

const inputSection = document.getElementById("inputSection");
const toggleLinkBtn = document.getElementById("toggleLinkBtn");
const toggleFileBtn = document.getElementById("toggleFileBtn");
const linkInputGroup = document.getElementById("linkInputGroup");
const fileInputGroup = document.getElementById("fileInputGroup");
const videoUrlInput = document.getElementById("videoUrlInput");
const videoFileInput = document.getElementById("videoFileInput");
const dropZone = document.getElementById("dropZone");
const uploadFileName = document.getElementById("uploadFileName");
const dashboardTargetLang = document.getElementById("dashboardTargetLang");
const startBtn = document.getElementById("startBtn");

const progressSection = document.getElementById("progressSection");
const currentStageLabel = document.getElementById("currentStageLabel");
const totalPercentLabel = document.getElementById("totalPercentLabel");
const progressBar = document.getElementById("progressBar");
const stageList = document.getElementById("stageList");
const stageDetailMsg = document.getElementById("stageDetailMsg");

const completedSection = document.getElementById("completedSection");
const finalDurationText = document.getElementById("finalDurationText");
const finalVideo = document.getElementById("finalVideo");
const viewVideoBtn = document.getElementById("viewVideoBtn");
const downloadVideoBtn = document.getElementById("downloadVideoBtn");
const downloadSrtBtn = document.getElementById("downloadSrtBtn");
const newJobBtn = document.getElementById("newJobBtn");
const currentJobIdLabel = document.getElementById("currentJobIdLabel");

const toastContainer = document.getElementById("toastContainer");

const historyBtn = document.getElementById("historyBtn");
const historyBadge = document.getElementById("historyBadge");
const historySection = document.getElementById("historySection");
const historyModal = document.getElementById("historyModal");
const closeHistoryBtn = document.getElementById("closeHistoryBtn");
const historyList = document.getElementById("historyList");
const historyModalList = document.getElementById("historyModalList");

const queuePanel = document.getElementById("queuePanel");
const queueList = document.getElementById("queueList");
const queueCount = document.getElementById("queueCount");

const subtitleEnabledToggle = document.getElementById("subtitleEnabledToggle");
const subtitleToggleStatus = document.getElementById("subtitleToggleStatus");

// ──────────────────────────────────────────────
// Toast
// ──────────────────────────────────────────────
function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerText = message;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ──────────────────────────────────────────────
// Subtitle Toggle
// ──────────────────────────────────────────────
subtitleEnabledToggle.addEventListener("change", () => {
  const enabled = subtitleEnabledToggle.checked;
  subtitleToggleStatus.textContent = enabled ? "ဖွင့်ထား" : "ပိတ်ထား";
  subtitleToggleStatus.className = "bv-toggle-status-pill " + (enabled ? "on" : "off");
});

// ──────────────────────────────────────────────
// Settings Tabs
// ──────────────────────────────────────────────
tabButtons.forEach(btn => {
  btn.addEventListener("click", () => {
    tabButtons.forEach(b => b.classList.remove("active"));
    tabContents.forEach(c => c.classList.remove("active"));
    btn.classList.add("active");
    const targetId = btn.getAttribute("data-tab");
    const targetContent = document.getElementById(targetId);
    if (targetContent) targetContent.classList.add("active");
  });
});

// ──────────────────────────────────────────────
// Aspect Ratio Switcher
// ──────────────────────────────────────────────
ratio916Btn.addEventListener("click", () => {
  ratio916Btn.classList.add("active");
  ratio169Btn.classList.remove("active");
  dragCanvasContainer.className = "bv-drag-canvas-frame ratio-9-16";
  updateSubtitleBadgePosition(subPosX, subPosY);
});

ratio169Btn.addEventListener("click", () => {
  ratio169Btn.classList.add("active");
  ratio916Btn.classList.remove("active");
  dragCanvasContainer.className = "bv-drag-canvas-frame ratio-16-9";
  updateSubtitleBadgePosition(subPosX, subPosY);
});

// ──────────────────────────────────────────────
// Subtitle Drag & Drop
// ──────────────────────────────────────────────
function updateSubtitleBadgePosition(xPct, yPct) {
  subPosX = Math.max(8, Math.min(92, xPct));
  subPosY = Math.max(6, Math.min(94, yPct));
  draggableSubtitle.style.left = `${subPosX}%`;
  draggableSubtitle.style.top = `${subPosY}%`;
  posXLabel.innerText = `${Math.round(subPosX)}%`;
  posYLabel.innerText = `${Math.round(subPosY)}%`;
}

async function autoSaveSubtitleSettings() {
  try {
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        subtitle_pos_x: subPosX,
        subtitle_pos_y: subPosY,
        font_style: fontStyleSelect.value,
        font_size_px: parseInt(fontSizeRange.value, 10),
        font_color: fontColorPicker.value,
        auto_blur_subtitles: Boolean(autoBlurSubtitlesToggle && autoBlurSubtitlesToggle.checked),
        output_resolution: outputResolution ? outputResolution.value : "1080p"
      })
    });
  } catch (e) {
    console.warn("Auto-save settings failed:", e);
  }
}

function handleDragMove(e) {
  if (!isDraggingSubtitle || (autoBlurSubtitlesToggle && autoBlurSubtitlesToggle.checked)) return;
  const rect = dragCanvasContainer.getBoundingClientRect();
  const clientX = e.clientX || (e.touches && e.touches[0].clientX);
  const clientY = e.clientY || (e.touches && e.touches[0].clientY);
  if (clientX === undefined || clientY === undefined) return;
  const rawX = ((clientX - rect.left) / rect.width) * 100;
  const rawY = ((clientY - rect.top) / rect.height) * 100;
  updateSubtitleBadgePosition(rawX, rawY);
}

draggableSubtitle.addEventListener("mousedown", (e) => { if (autoBlurSubtitlesToggle && autoBlurSubtitlesToggle.checked) return; isDraggingSubtitle = true; e.preventDefault(); });
draggableSubtitle.addEventListener("touchstart", () => { if (!(autoBlurSubtitlesToggle && autoBlurSubtitlesToggle.checked)) isDraggingSubtitle = true; }, { passive: true });
window.addEventListener("mousemove", handleDragMove);
window.addEventListener("touchmove", handleDragMove, { passive: true });
window.addEventListener("mouseup", () => { if (isDraggingSubtitle) { isDraggingSubtitle = false; autoSaveSubtitleSettings(); } });
window.addEventListener("touchend", () => { if (isDraggingSubtitle) { isDraggingSubtitle = false; autoSaveSubtitleSettings(); } });

resetPosBtn.addEventListener("click", () => {
  updateSubtitleBadgePosition(50.0, 82.0);
  autoSaveSubtitleSettings();
  showToast("စာတန်းထိုးနေရာကို Default (50%, 82%) သို့ ပြန်ထားပါပြီ။", "info");
});

// ──────────────────────────────────────────────
// Font & Color Live Preview
// ──────────────────────────────────────────────
function updateSubtitleVisualPreview() {
  const font = fontStyleSelect.value || "Z10-Cartoon";
  const color = fontColorPicker.value || "#FFFFFF";
  const sizePx = fontSizeRange.value || RESOLUTION_FONT_SIZES[outputResolution?.value] || 70;
  fontSizeDisplay.innerText = `${sizePx}px`;
  previewSubText.style.fontFamily = `"${font}", sans-serif`;
  previewSubText.style.color = color;
  const previewScaleSize = Math.max(12, Math.min(22, Math.round(sizePx * 0.45)));
  previewSubText.style.fontSize = `${previewScaleSize}px`;
  if (fontLivePreview) {
    fontLivePreview.style.fontFamily = `"${font}", sans-serif`;
    fontLivePreview.style.color = color;
    fontLivePreview.textContent = `ဒါက ${font} နဲ့ မြန်မာစာ preview ပါ`;
  }
}

fontStyleSelect.addEventListener("change", () => { updateSubtitleVisualPreview(); autoSaveSubtitleSettings(); });
fontSizeRange.addEventListener("input", updateSubtitleVisualPreview);
fontSizeRange.addEventListener("change", autoSaveSubtitleSettings);
fontColorPicker.addEventListener("input", (e) => { fontColorHex.innerText = e.target.value.toUpperCase(); updateSubtitleVisualPreview(); });
fontColorPicker.addEventListener("change", autoSaveSubtitleSettings);
if (autoBlurSubtitlesToggle) {
  autoBlurSubtitlesToggle.addEventListener("change", () => {
    applyAutoBlurUi(autoBlurSubtitlesToggle.checked);
    autoSaveSubtitleSettings();
  });
}

// ──────────────────────────────────────────────
// Load Fonts
// ──────────────────────────────────────────────
async function loadFonts() {
  try {
    const res = await fetch("/api/fonts");
    if (!res.ok) return;
    const data = await res.json();
    systemFonts = data.fonts || [];
    fontFiles = data.font_files || {};
    fontStyleSelect.innerHTML = "";
    systemFonts.forEach(font => {
      fontStyleSelect.appendChild(new Option(font, font));
      const url = fontFiles[font];
      if (url) {
        const face = new FontFace(font, `url(${url})`);
        face.load().then(loaded => document.fonts.add(loaded)).catch(err => console.warn("Font preview load failed", font, err));
      }
    });
    const currentFont = appSettings.font_style || "Z10-Cartoon";
    if (systemFonts.includes(currentFont)) fontStyleSelect.value = currentFont;
    updateSubtitleVisualPreview();
  } catch (err) { console.error("Error loading fonts:", err); }
}

function applyResolutionFontPreset() {
  const size = RESOLUTION_FONT_SIZES[outputResolution?.value] || 70;
  if (fontSizeRange) fontSizeRange.value = size;
  updateSubtitleVisualPreview();
}

if (outputResolution) outputResolution.addEventListener("change", () => {
  applyResolutionFontPreset();
  autoSaveSubtitleSettings();
});

uploadCustomFontBtn.addEventListener("click", () => customFontFileInput.click());
customFontFileInput.addEventListener("change", async () => {
  const file = customFontFileInput.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  uploadCustomFontBtn.innerText = "⏳ တင်နေပါသည်...";
  try {
    const res = await fetch("/api/fonts/upload", { method: "POST", body: formData });
    if (!res.ok) throw new Error("Font upload မအောင်မြင်ပါ");
    const data = await res.json();
    showToast(`Font ${data.font_name} အောင်မြင်စွာ တင်ပြီးပါပြီ!`, "success");
    await loadFonts();
    fontStyleSelect.value = data.font_name;
    updateSubtitleVisualPreview();
  } catch (err) {
    showToast(`Font upload error: ${err.message}`, "error");
  } finally {
    uploadCustomFontBtn.innerText = "+ Font အသစ်တင်မယ် (.ttf / .otf)";
  }
});

// ──────────────────────────────────────────────
// Load Languages
// ──────────────────────────────────────────────
async function loadLanguages() {
  try {
    const res = await fetch("/api/languages");
    if (!res.ok) return;
    const data = await res.json();
    targetLanguages = data.languages || [];
    dashboardTargetLang.innerHTML = "";
    settingsTargetLang.innerHTML = "";
    targetLanguages.forEach(lang => {
      dashboardTargetLang.appendChild(new Option(lang.name, lang.code));
      settingsTargetLang.appendChild(new Option(lang.name, lang.code));
    });
    const currentLang = appSettings.target_language || "my";
    dashboardTargetLang.value = currentLang;
    settingsTargetLang.value = currentLang;
  } catch (err) { console.error("Error loading languages:", err); }
}

dashboardTargetLang.addEventListener("change", (e) => { settingsTargetLang.value = e.target.value; syncLanguageToEdgeTTS(e.target.value); });
settingsTargetLang.addEventListener("change", (e) => { dashboardTargetLang.value = e.target.value; syncLanguageToEdgeTTS(e.target.value); });

function syncLanguageToEdgeTTS(langCode) {
  const found = targetLanguages.find(l => l.code === langCode);
  if (found && found.tts_locale && voiceCatalog.voices_by_language[found.tts_locale]) {
    edgeLanguageSelect.value = found.tts_locale;
    populateVoicesForLanguage(found.tts_locale);
  }
}

// ──────────────────────────────────────────────
// Load Voice Catalog
// ──────────────────────────────────────────────
async function loadVoiceCatalog() {
  try {
    const res = await fetch("/api/voices");
    if (!res.ok) return;
    const data = await res.json();
    voiceCatalog = { languages: data.edge_languages || [], voices_by_language: data.edge_voices_by_language || {} };
    edgeLanguageSelect.innerHTML = "";
    voiceCatalog.languages.forEach(lang => edgeLanguageSelect.appendChild(new Option(lang.name, lang.code)));
    const savedLang = data.current_edge_language || "my-MM";
    edgeLanguageSelect.value = savedLang;
    populateVoicesForLanguage(savedLang, data.current_edge_voice);
    if (data.current_voxcpm_voice_name) currentRefAudioName.innerText = data.current_voxcpm_voice_name;
    if (data.current_voxcpm_ref_text) voxcpmRefText.value = data.current_voxcpm_ref_text;
  } catch (err) { console.error("Error loading voices:", err); }
}

function populateVoicesForLanguage(langCode, selectVoiceId = null) {
  const voices = voiceCatalog.voices_by_language[langCode] || [];
  edgeVoiceSelect.innerHTML = "";
  if (voices.length === 0) { edgeVoiceSelect.appendChild(new Option("No voices available", "")); return; }
  voices.forEach(v => edgeVoiceSelect.appendChild(new Option(v.name, v.id)));
  if (selectVoiceId && voices.some(v => v.id === selectVoiceId)) edgeVoiceSelect.value = selectVoiceId;
}

edgeLanguageSelect.addEventListener("change", (e) => populateVoicesForLanguage(e.target.value));

// ──────────────────────────────────────────────
// Load Settings
// ──────────────────────────────────────────────
async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    if (!res.ok) return;
    appSettings = await res.json();
    if (appSettings.groq_api_key && groqApiKey) groqApiKey.placeholder = appSettings.groq_api_key;
    if (appSettings.gemini_api_key) geminiApiKey.placeholder = appSettings.gemini_api_key;
    if (appSettings.output_resolution && outputResolution) outputResolution.value = appSettings.output_resolution;
    if (appSettings.subtitle_animation && subtitleAnimationSelect) subtitleAnimationSelect.value = appSettings.subtitle_animation;
    if (appSettings.ai_mode && aiMode) aiMode.value = appSettings.ai_mode;
    if (appSettings.target_language) { dashboardTargetLang.value = appSettings.target_language; settingsTargetLang.value = appSettings.target_language; }
    if (appSettings.voice_engine) { voiceEngine.value = appSettings.voice_engine; toggleVoiceEngine(appSettings.voice_engine); }
    if (appSettings.font_color) { fontColorPicker.value = appSettings.font_color; fontColorHex.innerText = appSettings.font_color; }
    if (appSettings.font_size_px) { fontSizeRange.value = appSettings.font_size_px; fontSizeDisplay.innerText = `${appSettings.font_size_px}px`; }
    if (appSettings.font_style && fontStyleSelect.querySelector(`option[value="${appSettings.font_style}"]`)) fontStyleSelect.value = appSettings.font_style;
    applyResolutionFontPreset();
    if (autoBlurSubtitlesToggle) {
      autoBlurSubtitlesToggle.checked = Boolean(appSettings.auto_blur_subtitles);
      applyAutoBlurUi(autoBlurSubtitlesToggle.checked);
    }
    if (appSettings.subtitle_pos_x !== undefined && appSettings.subtitle_pos_y !== undefined) updateSubtitleBadgePosition(appSettings.subtitle_pos_x, appSettings.subtitle_pos_y);
    if (appSettings.voxcpm_voice_name) currentRefAudioName.innerText = appSettings.voxcpm_voice_name;
    if (appSettings.voxcpm_reference_text) voxcpmRefText.value = appSettings.voxcpm_reference_text;
    updateSubtitleVisualPreview();
  } catch (err) { console.error("Error loading settings:", err); }
}

function toggleVoiceEngine(engine) {
  if (engine === "voxcpm2") { edgeTtsSettingsBlock.style.display = "none"; voxcpmSettingsBlock.style.display = "block"; }
  else { edgeTtsSettingsBlock.style.display = "block"; voxcpmSettingsBlock.style.display = "none"; }
}

voiceEngine.addEventListener("change", (e) => toggleVoiceEngine(e.target.value));

uploadRefAudioBtn.addEventListener("click", () => voxcpmAudioFile.click());
voxcpmAudioFile.addEventListener("change", async () => {
  const file = voxcpmAudioFile.files[0];
  if (!file) return;
  const refText = voxcpmRefText.value.trim();
  if (!refText) {
    showToast("အသံဖိုင်ထဲက ပြောထားတဲ့ Reference Text ကို အရင်ထည့်ပါ။", "error");
    voxcpmRefText.focus();
    voxcpmAudioFile.value = "";
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  formData.append("reference_text", refText);
  uploadRefAudioBtn.innerText = "⏳ Uploading...";
  try {
    const res = await fetch("/api/voices/upload-reference", { method: "POST", body: formData });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(payload.detail || payload.message || `HTTP ${res.status}`);
    }
    const data = payload;
    currentRefAudioName.innerText = data.filename;
    showToast("Voice reference audio အောင်မြင်စွာ တင်ပြီးပါပြီ!", "success");
  } catch (err) {
    showToast(`Upload failed: ${err.message || "Network error"}`, "error");
    console.error("Reference audio upload failed", err);
  }
  finally { uploadRefAudioBtn.innerText = "📁 Upload Audio"; }
});

// ──────────────────────────────────────────────
// Save Settings
// ──────────────────────────────────────────────
settingsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    ai_mode: aiMode ? aiMode.value : "local",
    target_language: settingsTargetLang.value,
    voice_engine: voiceEngine.value,
    edge_tts_language: edgeLanguageSelect.value,
    edge_tts_voice: edgeVoiceSelect.value,
    voxcpm_reference_text: voxcpmRefText.value.trim(),
    font_color: fontColorPicker.value,
    font_size_px: parseInt(fontSizeRange.value, 10),
    font_style: fontStyleSelect.value,
    subtitle_pos_x: subPosX,
    subtitle_pos_y: subPosY,
    auto_blur_subtitles: Boolean(autoBlurSubtitlesToggle && autoBlurSubtitlesToggle.checked),
    subtitle_animation: subtitleAnimationSelect ? subtitleAnimationSelect.value : "fade",
    output_resolution: outputResolution ? outputResolution.value : "1080p"
  };
  const groqVal = groqApiKey ? groqApiKey.value.trim() : "";
  if (groqVal && !groqVal.includes("*")) payload.groq_api_key = groqVal;
  const geminiVal = geminiApiKey.value.trim();
  if (geminiVal && !geminiVal.includes("*")) payload.gemini_api_key = geminiVal;
  try {
    const res = await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!res.ok) throw new Error("Settings သိမ်းဆည်းခြင်း မအောင်မြင်ပါ");
    showToast("Settings အားလုံးကို အောင်မြင်စွာ သိမ်းဆည်းပြီးပါပြီ!", "success");
    settingsModal.classList.remove("active");
    await loadSettings();
  } catch (err) { showToast(`Error: ${err.message}`, "error"); }
});

openSettingsBtn.addEventListener("click", () => settingsModal.classList.add("active"));
closeSettingsBtn.addEventListener("click", () => settingsModal.classList.remove("active"));
cancelSettingsBtn.addEventListener("click", () => settingsModal.classList.remove("active"));
settingsModal.addEventListener("click", (e) => { if (e.target === settingsModal) settingsModal.classList.remove("active"); });

// ──────────────────────────────────────────────
// History Modal
// ──────────────────────────────────────────────
historyBtn.addEventListener("click", () => {
  renderHistoryModal();
  historyModal.classList.add("active");
});
closeHistoryBtn.addEventListener("click", () => historyModal.classList.remove("active"));
historyModal.addEventListener("click", (e) => { if (e.target === historyModal) historyModal.classList.remove("active"); });

function renderHistoryModal() {
  const jobs = Object.values(allJobs)
    .filter(j => j.status === "completed" || j.status === "failed")
    .sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
  const html = jobs.length === 0 ? `<p class="bv-empty-state">History မရှိသေးပါ</p>` : jobs.map(j => {
    const label = j.video_url || j.uploaded_filename || j.job_id;
    const short = label.length > 55 ? label.slice(0, 52) + "..." : label;
    const icon = j.status === "completed" ? "✅" : j.status === "failed" ? "❌" : "⏳";
    const iconClass = j.status === "completed" ? "completed" : j.status === "failed" ? "failed" : "running";
    const timeStr = j.created_at ? new Date(j.created_at * 1000).toLocaleString() : "";
    const videoUrl = `/api/jobs/${j.job_id}/files/final_video.mp4`;
    const srtUrl = `/api/jobs/${j.job_id}/files/subtitles.srt`;
    const completedActions = j.status === "completed"
      ? `<a class="bv-history-action-btn" href="${videoUrl}" target="_blank">▶ Preview</a>
         <a class="bv-history-action-btn" href="${videoUrl}" download="recap_${j.job_id}.mp4">⬇ Video</a>
         <a class="bv-history-action-btn" href="${srtUrl}" download="subtitles_${j.job_id}.srt">📄 SRT</a>`
      : j.status === "running" || j.status === "pending"
      ? `<button class="bv-history-action-btn" onclick="switchToJob('${j.job_id}')">👁 ကြည့်မည်</button>`
      : `<span style="font-size:0.72rem;color:var(--text-muted);">${j.error ? cleanUserStatusMessage(j.error).slice(0, 40) : "Failed"}</span>`;
    return `<div class="bv-history-item">
      <div class="bv-history-item-icon ${iconClass}">${icon}</div>
      <div class="bv-history-item-body">
        <div class="bv-history-item-title" title="${label}">${short}</div>
        <div class="bv-history-item-meta">${j.status} • ${timeStr}</div>
      </div>
      <div class="bv-history-item-actions">${completedActions}</div>
    </div>`;
  }).join("");
  if (historyList) historyList.innerHTML = html;
  if (historyModalList) historyModalList.innerHTML = html;
}

function updateHistoryBadge() {
  const count = Object.values(allJobs).filter(j => j.status === "completed" || j.status === "failed").length;
  if (count > 0) {
    historyBadge.textContent = count;
    historyBadge.style.display = "inline-block";
    if (historySection) historySection.style.display = "block";
  } else {
    historyBadge.style.display = "none";
    if (historySection) historySection.style.display = "none";
  }
  renderHistoryModal();
}

// ──────────────────────────────────────────────
// Queue Panel
// ──────────────────────────────────────────────
function renderQueuePanel() {
  const activeJobs = Object.values(allJobs).filter(j => j.status === "running" || j.status === "pending" || j.status === "queued");
  if (activeJobs.length === 0) {
    queuePanel.style.display = "none";
    return;
  }
  queuePanel.style.display = "block";
  queueCount.textContent = activeJobs.length;

  queueList.innerHTML = activeJobs.sort((a, b) => (a.created_at || 0) - (b.created_at || 0)).map(j => {
    const label = j.video_url || j.uploaded_filename || j.job_id;
    const short = label.length > 50 ? label.slice(0, 47) + "..." : label;
    const dotClass = j.status === "running" ? "running" : "pending";
    const stage = j.stage || (j.status === "queued" ? "Queue တွင် စောင့်ဆိုင်းနေပါသည်..." : "");
    const prog = Math.round((j.progress || 0) * 100) / 100;
    const isActive = j.job_id === activeJobId;
    const btnHtml = isActive
      ? `<span style="font-size:0.72rem;color:var(--primary);font-weight:700;">ကြည့်နေသည်</span>`
      : `<button class="bv-queue-view-btn" onclick="switchToJob('${j.job_id}')">ကြည့်မည်</button>`;
    return `<div class="bv-queue-item">
      <span class="bv-queue-status-dot ${dotClass}"></span>
      <div class="bv-queue-item-info">
        <div class="bv-queue-item-url">${short}</div>
        <div class="bv-queue-item-stage">${stage}</div>
      </div>
      <div class="bv-queue-mini-bar"><div class="bv-queue-mini-fill" style="width:${prog}%"></div></div>
      ${btnHtml}
    </div>`;
  }).join("");
}

// Switch main view to another job
function switchToJob(jobId) {
  historyModal.classList.remove("active");
  const job = allJobs[jobId];
  if (!job) return;

  activeJobId = jobId;
  saveActiveJobToStorage(jobId);

  if (job.status === "completed") {
    showCompletedView(jobId, job.summary || {});
  } else if (job.status === "failed") {
    showToast(`Job ${jobId}: ${cleanUserStatusMessage(job.error || "Failed")}`, "error");
  } else {
    // running / pending / queued
    inputSection.style.display = "none";
    completedSection.style.display = "none";
    progressSection.style.display = "block";
    if (job.stage) updateProgressUI(job.stage, job.stage_index || 1, job.progress || 0, job.stage);
    connectSSE(jobId);
  }
  renderQueuePanel();
  updateActiveJobBanner();
}

// ──────────────────────────────────────────────
// localStorage job persistence (refresh-proof)
// ──────────────────────────────────────────────
const STORAGE_KEY_ACTIVE = "recap_active_job_id";
const STORAGE_KEY_JOBS = "recap_jobs_map";

function saveActiveJobToStorage(jobId) {
  if (jobId) localStorage.setItem(STORAGE_KEY_ACTIVE, jobId);
  else localStorage.removeItem(STORAGE_KEY_ACTIVE);
}

function saveJobsToStorage() {
  try {
    localStorage.setItem(STORAGE_KEY_JOBS, JSON.stringify(allJobs));
  } catch (e) { /* quota exceeded, ignore */ }
}

function loadJobsFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_JOBS);
    if (raw) return JSON.parse(raw);
  } catch (e) {}
  return {};
}

function getStoredActiveJobId() {
  return localStorage.getItem(STORAGE_KEY_ACTIVE) || null;
}

// ──────────────────────────────────────────────
// Check GPU Status
// ──────────────────────────────────────────────
async function checkGpuStatus() {
  try {
    const res = await fetch("/api/gpu");
    if (!res.ok) return;
    const data = await res.json();
    const gpuEl = document.getElementById("gpuStatusText");
    if (gpuEl) {
      const hardware = data.gpu_accelerated ? "NVIDIA NVENC (GPU)" : "libx264 (CPU Fallback)";
      gpuEl.innerText = `AI Recap Studio • ${data.gpu_accelerated ? "⚡ " : ""}${hardware}`;
    }
  } catch (e) {}
}

// ──────────────────────────────────────────────
// Restore jobs from server on page load
// ──────────────────────────────────────────────
async function restoreJobsOnLoad() {
  // Load cached jobs from localStorage first (for instant display)
  const cached = loadJobsFromStorage();
  Object.assign(allJobs, cached);
  updateHistoryBadge();
  renderQueuePanel();

  // Then fetch fresh data from server
  try {
    const res = await fetch("/api/jobs");
    if (!res.ok) return;
    const data = await res.json();
    for (const j of (data.jobs || [])) {
      allJobs[j.job_id] = { ...(allJobs[j.job_id] || {}), ...j };
    }
    saveJobsToStorage();
    updateHistoryBadge();
    renderQueuePanel();
  } catch (e) { console.warn("Could not fetch jobs list:", e); }

  // Check active jobs and connect SSE
  let hasRunning = false;
  for (const [jid, jstate] of Object.entries(allJobs)) {
    if (jstate.status === "running" || jstate.status === "pending" || jstate.status === "queued") {
      hasRunning = true;
      connectSSEBackground(jid);
    }
  }

  // Restore active job view if stored
  const storedActiveId = getStoredActiveJobId();
  if (storedActiveId && allJobs[storedActiveId]) {
    const job = allJobs[storedActiveId];
    if (job.status === "completed") {
      showCompletedView(storedActiveId, job.summary || {});
    } else if (job.status === "running" || job.status === "pending" || job.status === "queued") {
      activeJobId = storedActiveId;
      inputSection.style.display = "none";
      progressSection.style.display = "block";
      completedSection.style.display = "none";
      if (job.stage) updateProgressUI(job.stage, job.stage_index || 1, job.progress || 0, job.stage);
      connectSSE(storedActiveId);
    }
  }

  updateActiveJobBanner();
}

// ──────────────────────────────────────────────
// Input Mode Toggles
// ──────────────────────────────────────────────
toggleLinkBtn.addEventListener("click", () => {
  currentInputMode = "link";
  toggleLinkBtn.classList.add("active");
  toggleFileBtn.classList.remove("active");
  linkInputGroup.style.display = "block";
  fileInputGroup.style.display = "none";
});

toggleFileBtn.addEventListener("click", () => {
  currentInputMode = "file";
  toggleFileBtn.classList.add("active");
  toggleLinkBtn.classList.remove("active");
  fileInputGroup.style.display = "block";
  linkInputGroup.style.display = "none";
});

dropZone.addEventListener("click", () => videoFileInput.click());
videoFileInput.addEventListener("change", () => {
  if (videoFileInput.files.length > 0) uploadFileName.innerText = videoFileInput.files[0].name;
});

// ──────────────────────────────────────────────
// Progress UI
// ──────────────────────────────────────────────
function updateProgressUI(stageName, stageIdx, percent, message) {
  const safeMessage = cleanUserStatusMessage(message || stageName || "...");
  if (currentStageLabel) currentStageLabel.innerText = cleanUserStatusMessage(stageName || "...");
  if (stageDetailMsg) stageDetailMsg.innerText = safeMessage;
  const totalStages = BURMESE_STAGES.length;
  const totalOverall = Math.min(100, Math.max(0, ((stageIdx - 1) / totalStages) * 100 + (percent / totalStages)));
  if (totalPercentLabel) totalPercentLabel.innerText = `${Math.round(totalOverall)}%`;
  if (progressBar) progressBar.style.width = `${totalOverall}%`;

  const chips = stageList.querySelectorAll(".bv-step-chip");
  chips.forEach((chip, idx) => {
    const num = idx + 1;
    const numEl = chip.querySelector(".bv-chip-num");
    if (num < stageIdx) {
      chip.className = "bv-step-chip completed";
      if (numEl) numEl.innerText = "✓";
    } else if (num === stageIdx) {
      chip.className = "bv-step-chip active";
      if (numEl) numEl.innerText = num;
    } else {
      chip.className = "bv-step-chip";
      if (numEl) numEl.innerText = num;
    }
  });

  if (stageName === BURMESE_STAGES[7]) {
    if (progressBar) progressBar.style.width = "100%";
    if (totalPercentLabel) totalPercentLabel.innerText = "100%";
  }
}

// ──────────────────────────────────────────────
// Show Completed View
// ──────────────────────────────────────────────
function showCompletedView(jobId, summaryData) {
  activeJobId = jobId;
  saveActiveJobToStorage(jobId);

  inputSection.style.display = "none";
  progressSection.style.display = "none";
  completedSection.style.display = "block";

  const videoUrl = `/api/jobs/${jobId}/files/final_video.mp4`;
  const srtUrl = `/api/jobs/${jobId}/files/subtitles.srt`;

  finalVideo.src = videoUrl;
  downloadVideoBtn.href = videoUrl;
  downloadVideoBtn.setAttribute("download", `recap_${jobId}.mp4`);
  downloadSrtBtn.href = srtUrl;
  downloadSrtBtn.setAttribute("download", `subtitles_${jobId}.srt`);

  if (currentJobIdLabel) currentJobIdLabel.textContent = jobId;

  if (summaryData && summaryData.final_duration_formatted) {
    finalDurationText.innerText = summaryData.final_duration_formatted;
  }

  // Check if SRT file actually exists, hide button if not
  fetch(srtUrl, { method: "HEAD" }).then(r => {
    downloadSrtBtn.style.display = r.ok ? "inline-flex" : "none";
  }).catch(() => { downloadSrtBtn.style.display = "none"; });
}

// ──────────────────────────────────────────────
// Add to Queue / Multitasking Navigation
// ──────────────────────────────────────────────
const addAnotherJobBtn = document.getElementById("addAnotherJobBtn");
const activeJobNotice = document.getElementById("activeJobNotice");
const activeJobNoticeText = document.getElementById("activeJobNoticeText");
const viewCurrentActiveBtn = document.getElementById("viewCurrentActiveBtn");

function updateActiveJobBanner() {
  if (!activeJobNotice) return;
  const runningJob = Object.values(allJobs).find(j => j.status === "running" || j.status === "pending");
  if (runningJob && inputSection.style.display !== "none") {
    activeJobNotice.style.display = "flex";
    const lbl = runningJob.video_url || runningJob.uploaded_filename || runningJob.job_id;
    const shortLbl = lbl.length > 32 ? lbl.slice(0, 29) + "..." : lbl;
    if (activeJobNoticeText) {
      activeJobNoticeText.innerText = `ဗီဒီယို တစ်ပုဒ် (${shortLbl}) လုပ်ဆောင်နေဆဲဖြစ်သည် • Queue ထဲသို့ နောက်ထပ် ဗီဒီယိုများ ထည့်သွင်းနိုင်ပါသည်`;
    }
  } else {
    activeJobNotice.style.display = "none";
  }
}

if (addAnotherJobBtn) {
  addAnotherJobBtn.addEventListener("click", () => {
    progressSection.style.display = "none";
    inputSection.style.display = "block";
    videoUrlInput.value = "";
    videoFileInput.value = "";
    uploadFileName.innerText = "ဗီဒီယိုဖိုင် ရွေးချယ်ရန် နှိပ်ပါ သို့မဟုတ် ဖိုင်ဆွဲထည့်ပါ";
    updateActiveJobBanner();
    videoUrlInput.focus();
  });
}

if (viewCurrentActiveBtn) {
  viewCurrentActiveBtn.addEventListener("click", () => {
    const runningJob = Object.values(allJobs).find(j => j.status === "running" || j.status === "pending");
    if (runningJob) {
      switchToJob(runningJob.job_id);
    }
  });
}

// ──────────────────────────────────────────────
// Start Pipeline & Add to Queue
// ──────────────────────────────────────────────
startBtn.addEventListener("click", async () => {
  if ((appSettings.ai_mode || "local") === "cloud" && !appSettings.has_gemini_key) {
    showToast("Gemini API Key ကို Settings တွင် အရင်ထည့်သွင်းပေးပါ။", "error");
    settingsModal.classList.add("active");
    return;
  }

  const chosenTargetLang = dashboardTargetLang.value || "my";
  const subtitleEnabled = subtitleEnabledToggle.checked;
  const isAnotherJobRunning = Object.values(allJobs).some(j => j.status === "running" || j.status === "pending");

  if (currentInputMode === "link") {
    const url = videoUrlInput.value.trim();
    if (!url) { showToast("Video Link ထည့်သွင်းပေးပါ။", "error"); videoUrlInput.focus(); return; }

    startBtn.disabled = true;
    startBtn.innerText = "ထည့်သွင်းနေပါသည်...";

    try {
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video_url: url,
          target_language: chosenTargetLang,
          output_resolution: outputResolution ? outputResolution.value : "1080p",
          subtitle_pos_x: subPosX,
          subtitle_pos_y: subPosY,
          font_style: fontStyleSelect.value,
          font_size_px: parseInt(fontSizeRange.value, 10),
          font_color: fontColorPicker.value,
          subtitle_animation: subtitleAnimationSelect ? subtitleAnimationSelect.value : "fade",
          subtitle_enabled: subtitleEnabled
        })
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Job creation failed"); }
      const data = await res.json();
      const newJobId = data.job_id;

      if (isAnotherJobRunning) {
        // Enqueued job: stay on form or let user know
        allJobs[newJobId] = {
          job_id: newJobId,
          video_url: url,
          status: "queued",
          stage: "တန်းစီဇယားတွင် စောင့်ဆိုင်းနေပါသည်...",
          progress: 0,
          created_at: Date.now() / 1000
        };
        saveJobsToStorage();
        updateHistoryBadge();
        renderQueuePanel();
        connectSSEBackground(newJobId);
        showToast(`Queue ထဲသို့ အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ (နံပါတ် #${data.queue_position || 'Queue'})!`, "success");
        videoUrlInput.value = "";
        updateActiveJobBanner();
      } else {
        // Direct execution: switch to progress view
        activeJobId = newJobId;
        allJobs[newJobId] = {
          job_id: newJobId,
          video_url: url,
          status: "running",
          stage: BURMESE_STAGES[0],
          progress: 0,
          created_at: Date.now() / 1000
        };
        saveActiveJobToStorage(newJobId);
        saveJobsToStorage();
        updateHistoryBadge();
        renderQueuePanel();
        inputSection.style.display = "none";
        progressSection.style.display = "block";
        completedSection.style.display = "none";
        updateProgressUI(BURMESE_STAGES[0], 1, 0, "စတင်နေပါသည်...");
        connectSSE(newJobId);
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    } finally {
      startBtn.disabled = false;
      startBtn.innerHTML = `<span>စတင်မယ်</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="bv-btn-arrow"><polyline points="9 18 15 12 9 6"/></svg>`;
    }

  } else {
    const file = videoFileInput.files[0];
    if (!file) { showToast("ဗီဒီယိုဖိုင် ရွေးချယ်ပေးပါ။", "error"); return; }

    startBtn.disabled = true;
    startBtn.innerText = "ဖိုင်ပေးပို့နေပါသည်...";

    const formData = new FormData();
    formData.append("file", file);
    formData.append("target_language", chosenTargetLang);
    formData.append("output_resolution", outputResolution ? outputResolution.value : "1080p");
    formData.append("subtitle_pos_x", subPosX);
    formData.append("subtitle_pos_y", subPosY);
    formData.append("font_style", fontStyleSelect.value);
    formData.append("font_size_px", parseInt(fontSizeRange.value, 10));
    formData.append("font_color", fontColorPicker.value);
    formData.append("subtitle_animation", subtitleAnimationSelect ? subtitleAnimationSelect.value : "fade");
    formData.append("subtitle_enabled", subtitleEnabled ? "true" : "false");

    try {
      const res = await fetch("/api/jobs/upload", { method: "POST", body: formData });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Upload job failed"); }
      const data = await res.json();
      const newJobId = data.job_id;

      if (isAnotherJobRunning) {
        allJobs[newJobId] = {
          job_id: newJobId,
          uploaded_filename: file.name,
          status: "queued",
          stage: "တန်းစီဇယားတွင် စောင့်ဆိုင်းနေပါသည်...",
          progress: 0,
          created_at: Date.now() / 1000
        };
        saveJobsToStorage();
        updateHistoryBadge();
        renderQueuePanel();
        connectSSEBackground(newJobId);
        showToast(`Queue ထဲသို့ အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ (နံပါတ် #${data.queue_position || 'Queue'})!`, "success");
        videoFileInput.value = "";
        uploadFileName.innerText = "ဗီဒီယိုဖိုင် ရွေးချယ်ရန် နှိပ်ပါ သို့မဟုတ် ဖိုင်ဆွဲထည့်ပါ";
        updateActiveJobBanner();
      } else {
        activeJobId = newJobId;
        allJobs[newJobId] = {
          job_id: newJobId,
          uploaded_filename: file.name,
          status: "running",
          stage: BURMESE_STAGES[0],
          progress: 0,
          created_at: Date.now() / 1000
        };
        saveActiveJobToStorage(newJobId);
        saveJobsToStorage();
        updateHistoryBadge();
        renderQueuePanel();
        inputSection.style.display = "none";
        progressSection.style.display = "block";
        completedSection.style.display = "none";
        updateProgressUI(BURMESE_STAGES[0], 1, 0, "ဗီဒီယိုဖိုင် ပေးပို့နေပါသည်...");
        connectSSE(newJobId);
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    } finally {
      startBtn.disabled = false;
      startBtn.innerHTML = `<span>စတင်မယ်</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="bv-btn-arrow"><polyline points="9 18 15 12 9 6"/></svg>`;
    }
  }
});

// ──────────────────────────────────────────────
// SSE - Main view job
// ──────────────────────────────────────────────
function startJobPolling(jobId) {
  if (jobPollers[jobId]) return;
  const poll = async () => {
    try {
      const res = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
      if (!res.ok) return;
      const job = await res.json();
      if (!allJobs[jobId]) allJobs[jobId] = { job_id: jobId };
      allJobs[jobId] = { ...allJobs[jobId], ...job };
      saveJobsToStorage();
      renderQueuePanel();
      if (jobId === activeJobId && job.stage) {
        updateProgressUI(job.stage, job.stage_index || 1, job.progress || 0, job.message || job.stage);
      }
      if (job.status === "completed" || job.status === "failed") {
        clearInterval(jobPollers[jobId]);
        delete jobPollers[jobId];
        if (job.status === "completed" && jobId === activeJobId && job.summary) showCompletedView(jobId, job.summary);
        if (job.status === "failed" && jobId === activeJobId) {
          showToast(`မအောင်မြင်ပါ: ${cleanUserStatusMessage(job.error || "Job failed")}`, "error");
          inputSection.style.display = "block";
          progressSection.style.display = "none";
          saveActiveJobToStorage(null);
        }
      }
    } catch (err) { console.warn("Job status polling failed", err); }
  };
  poll();
  jobPollers[jobId] = setInterval(poll, 2000);
}

function connectSSE(jobId) {
  if (currentEventSource) { try { currentEventSource.close(); } catch (e) {} }

  currentEventSource = new EventSource(`/api/jobs/${jobId}/stream`);
  startJobPolling(jobId);

  currentEventSource.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      const stage = event.stage;
      const stageIdx = event.stage_index || 1;
      const progress = event.progress || 0;
      const message = cleanUserStatusMessage(event.message || stage);
      const data = event.data || {};

      // Update allJobs state
      if (allJobs[jobId]) {
        allJobs[jobId].stage = stage;
        allJobs[jobId].stage_index = stageIdx;
        allJobs[jobId].progress = progress;
        allJobs[jobId].status = "running";
      }
      saveJobsToStorage();
      renderQueuePanel();

      // Update UI only if this is the currently watched job
      if (jobId === activeJobId) {
        updateProgressUI(stage, stageIdx, progress, message);
      }

      if (stage === BURMESE_STAGES[7]) {
        currentEventSource.close();
        if (jobPollers[jobId]) { clearInterval(jobPollers[jobId]); delete jobPollers[jobId]; }
        if (allJobs[jobId]) {
          allJobs[jobId].status = "completed";
          allJobs[jobId].summary = data;
        }
        saveJobsToStorage();
        renderQueuePanel();
        updateHistoryBadge();

        if (jobId === activeJobId) {
          showCompletedView(jobId, data);
        }
        showToast(`ဗီဒီယို [${jobId}] အောင်မြင်စွာ ပြုလုပ်ပြီးပါပြီ!`, "success");
      }

      if (stage === "မအောင်မြင်ပါ") {
        currentEventSource.close();
        if (jobPollers[jobId]) { clearInterval(jobPollers[jobId]); delete jobPollers[jobId]; }
        if (allJobs[jobId]) { allJobs[jobId].status = "failed"; allJobs[jobId].error = data.error || message; }
        saveJobsToStorage();
        renderQueuePanel();
        updateHistoryBadge();
        if (jobId === activeJobId) {
          showToast(`မအောင်မြင်ပါ: ${data.error || message}`, "error");
          inputSection.style.display = "block";
          progressSection.style.display = "none";
          saveActiveJobToStorage(null);
        }
      }
    } catch (err) { console.error("SSE parse error:", err); }
  };

  currentEventSource.onerror = () => {
    // Cloudflare may reconnect/buffer SSE; the REST poller remains authoritative.
    const job = allJobs[jobId];
    if (job && job.status !== "completed" && job.status !== "failed") {
      setTimeout(() => {
        if (allJobs[jobId] && allJobs[jobId].status !== "completed" && allJobs[jobId].status !== "failed") {
          connectSSE(jobId);
        }
      }, 3000);
    }
  };
}

// SSE for background (queue) jobs - only updates allJobs state
function connectSSEBackground(jobId) {
  if (jobEventSources[jobId]) return;
  const es = new EventSource(`/api/jobs/${jobId}/stream`);
  jobEventSources[jobId] = es;

  es.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      const stage = event.stage;
      if (allJobs[jobId]) {
        allJobs[jobId].stage = stage;
        allJobs[jobId].stage_index = event.stage_index || 1;
        allJobs[jobId].progress = event.progress || 0;
      }
      if (stage === BURMESE_STAGES[7]) {
        if (allJobs[jobId]) { allJobs[jobId].status = "completed"; allJobs[jobId].summary = event.data || {}; }
        saveJobsToStorage(); renderQueuePanel(); updateHistoryBadge();
        es.close(); delete jobEventSources[jobId];
        showToast(`Background job [${jobId}] ပြီးပါပြီ!`, "success");
      } else if (stage === "မအောင်မြင်ပါ") {
        if (allJobs[jobId]) { allJobs[jobId].status = "failed"; }
        saveJobsToStorage(); renderQueuePanel();
        es.close(); delete jobEventSources[jobId];
      } else {
        saveJobsToStorage(); renderQueuePanel();
      }
    } catch (err) {}
  };
  es.onerror = () => {};
}

// ──────────────────────────────────────────────
// Completed Section Buttons
// ──────────────────────────────────────────────
viewVideoBtn.addEventListener("click", () => {
  finalVideo.play();
  finalVideo.scrollIntoView({ behavior: "smooth" });
});

newJobBtn.addEventListener("click", () => {
  completedSection.style.display = "none";
  inputSection.style.display = "block";
  videoUrlInput.value = "";
  videoFileInput.value = "";
  uploadFileName.innerText = "ဗီဒီယိုဖိုင် ရွေးချယ်ရန် နှိပ်ပါ သို့မဟုတ် ဖိုင်ဆွဲထည့်ပါ";
  saveActiveJobToStorage(null);
});

// ──────────────────────────────────────────────
// Initialization
// ──────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  await checkGpuStatus();
  await loadVoiceCatalog();
  await loadFonts();
  await loadLanguages();
  await loadSettings();
  await restoreJobsOnLoad();
});
