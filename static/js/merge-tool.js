(() => {
  const input = document.getElementById('mergeFiles');
  const drop = document.getElementById('mergeDrop');
  const list = document.getElementById('clipList');
  const count = document.getElementById('mergeCount');
  const preview = document.getElementById('mergePreview');
  const empty = document.getElementById('mergePreviewEmpty');
  const exportBtn = document.getElementById('mergeExport');
  const status = document.getElementById('mergeStatus');
  const error = document.getElementById('mergeError');
  const output = document.getElementById('mergeOutput');
  const outputVideo = document.getElementById('mergeOutputVideo');
  const download = document.getElementById('mergeDownload');
  const timeline = document.getElementById('mergeTimeline');
  const timelineTime = document.getElementById('timelineTime');
  const playSequenceBtn = document.getElementById('playSequenceBtn');
  const profile = document.getElementById('mergeProfile');
  const layout = document.getElementById('mergeLayout');
  const fps = document.getElementById('mergeFps');
  let clips = [];
  let previewUrl = null;
  let previewIndex = 0;
  let pointerDragIndex = null;

  const esc = (value) => String(value).replace(/[&<>'"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const fmt = (seconds) => { if (!Number.isFinite(seconds)) return '--:--'; const s = Math.round(seconds); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
  const totalDuration = () => clips.reduce((sum, clip) => sum + Math.max(0, (clip.end || clip.duration) - clip.start), 0);
  const setError = (message = '') => { error.textContent = message; };

  function render() {
    count.textContent = `${clips.length} / 3`;
    exportBtn.disabled = clips.length < 2 || clips.length > 3;
    if (!clips.length) { list.innerHTML = '<div class="merge-empty">ဖိုင်ရွေးပြီးရင် preview ဒီနေရာမှာပေါ်ပါမယ်</div>'; return; }
    list.innerHTML = clips.map((clip, i) => `<div class="clip-item" data-index="${i}">
      <div class="clip-number">${i + 1}</div><div class="clip-thumb"><video src="${clip.url}" muted></video></div>
      <div class="clip-main"><strong>${esc(clip.file.name)}</strong><small>${clip.duration ? fmt(clip.duration) : 'ဖတ်နေသည်...'}</small>
        <div class="clip-controls"><label>Start <input class="clip-start" type="number" min="0" step="0.1" value="${clip.start}"></label><label>End <input class="clip-end" type="number" min="0.1" step="0.1" value="${clip.end || ''}" placeholder="end"></label><label>Volume <input class="clip-volume" type="range" min="0" max="1.5" step="0.05" value="${clip.volume}"></label></div>
      </div><div class="clip-actions"><button class="clip-up" ${i === 0 ? 'disabled' : ''}>↑</button><button class="clip-down" ${i === clips.length - 1 ? 'disabled' : ''}>↓</button><button class="clip-remove">×</button></div>
    </div>`).join('');
    list.querySelectorAll('.clip-item').forEach((row) => {
      const i = Number(row.dataset.index); const clip = clips[i];
      row.querySelector('.clip-start').addEventListener('input', (e) => clip.start = Math.max(0, Number(e.target.value) || 0));
      row.querySelector('.clip-end').addEventListener('input', (e) => clip.end = Number(e.target.value) || clip.duration);
      row.querySelector('.clip-volume').addEventListener('input', (e) => clip.volume = Number(e.target.value));
      row.querySelector('.clip-up').addEventListener('click', () => { [clips[i - 1], clips[i]] = [clips[i], clips[i - 1]]; render(); });
      row.querySelector('.clip-down').addEventListener('click', () => { [clips[i], clips[i + 1]] = [clips[i + 1], clips[i]]; render(); });
      row.querySelector('.clip-remove').addEventListener('click', () => { URL.revokeObjectURL(clip.url); clips.splice(i, 1); render(); updatePreview(); });
    });
    renderTimeline();
  }

  function renderTimeline() {
    if (!timeline) return;
    if (!clips.length) { timeline.innerHTML = '<div class="timeline-empty">Clip တွေထည့်ရင် timeline ပေါ်လာပါမယ်</div>'; return; }
    const total = Math.max(0.1, totalDuration());
    timeline.innerHTML = clips.map((clip, i) => {
      const duration = Math.max(0.1, (clip.end || clip.duration) - clip.start);
      return `<div class="timeline-clip" draggable="true" data-index="${i}" style="--clip-width:${Math.max(150, duration / total * 720)}px"><span class="timeline-clip-index">${i + 1}</span><strong>${esc(clip.file.name)}</strong><small>${fmt(duration)}</small></div>`;
    }).join('') + '<div id="timelinePlayhead" class="timeline-playhead"></div>';
    timeline.querySelectorAll('.timeline-clip').forEach((block) => {
      const index = Number(block.dataset.index);
      block.addEventListener('dragstart', (event) => event.dataTransfer.setData('text/plain', String(index)));
      block.addEventListener('dragover', (event) => event.preventDefault());
      block.addEventListener('drop', (event) => {
        event.preventDefault(); const from = Number(event.dataTransfer.getData('text/plain'));
        if (Number.isInteger(from) && from !== index) { const [moved] = clips.splice(from, 1); clips.splice(index, 0, moved); render(); updatePreview(); }
      });
      block.addEventListener('pointerdown', () => { pointerDragIndex = index; block.classList.add('is-dragging'); });
    });
    timeline.onclick = seekTimeline;
  }

  document.addEventListener('pointerup', (event) => {
    if (pointerDragIndex === null || !timeline) return;
    const from = pointerDragIndex;
    pointerDragIndex = null;
    timeline.querySelectorAll('.timeline-clip').forEach((item) => item.classList.remove('is-dragging'));
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.timeline-clip');
    const to = target ? Number(target.dataset.index) : from;
    if (Number.isInteger(to) && from !== to && clips[from]) {
      const [moved] = clips.splice(from, 1);
      clips.splice(to, 0, moved);
      render();
      updatePreview();
    }
  });

  function seekTimeline(event) {
    if (!clips.length || event.target.closest('.timeline-clip')) return;
    const rect = timeline.getBoundingClientRect();
    const target = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * totalDuration();
    let cursor = 0;
    for (let i = 0; i < clips.length; i += 1) {
      const duration = Math.max(0.1, (clips[i].end || clips[i].duration) - clips[i].start);
      if (target <= cursor + duration || i === clips.length - 1) {
        previewIndex = i; preview.src = clips[i].url; preview.currentTime = Math.max(0, target - cursor); preview.play().catch(() => {}); break;
      }
      cursor += duration;
    }
  }

  function updateTimelinePosition() {
    if (!timeline || !clips.length) return;
    const before = clips.slice(0, previewIndex).reduce((sum, clip) => sum + Math.max(0, (clip.end || clip.duration) - clip.start), 0);
    const global = before + (preview.currentTime || 0);
    const total = Math.max(0.1, totalDuration());
    const head = document.getElementById('timelinePlayhead');
    if (head) head.style.left = `${Math.min(100, Math.max(0, global / total * 100))}%`;
    if (timelineTime) timelineTime.textContent = `${fmt(global)} / ${fmt(total)}`;
  }

  function updatePreview() {
    previewIndex = 0;
    previewUrl = clips[0]?.url || null;
    preview.pause();
    preview.removeAttribute('src');
    preview.load();
    if (previewUrl) preview.src = previewUrl;
    empty.hidden = Boolean(previewUrl);
    status.textContent = clips.length >= 2 ? 'Sequential preview ready' : 'Add 2–3 clips';
  }

  // Preview the exact merge order: clip 1 ends, then clip 2 starts, then clip 3.
  // This is intentionally sequential playback, not split-screen or overlay.
  preview.addEventListener('ended', () => {
    if (!clips.length || previewIndex >= clips.length - 1) {
      status.textContent = clips.length >= 2 ? 'Sequential preview complete' : 'Add 2–3 clips';
      return;
    }
    previewIndex += 1;
    const nextUrl = clips[previewIndex].url;
    preview.pause();
    preview.src = nextUrl;
    preview.load();
    preview.onloadedmetadata = () => { preview.onloadedmetadata = null; preview.play().catch(() => {}); };
  });
  preview.addEventListener('timeupdate', updateTimelinePosition);
  if (playSequenceBtn) playSequenceBtn.addEventListener('click', () => {
    if (!clips.length) return;
    previewIndex = 0;
    preview.src = clips[0].url;
    preview.load();
    preview.onloadedmetadata = () => { preview.onloadedmetadata = null; preview.play().catch(() => {}); };
  });

  function addFiles(files) {
    const available = [...files].filter((file) => file.type.startsWith('video/')).slice(0, 3 - clips.length);
    available.forEach((file) => {
      const clip = { file, url: URL.createObjectURL(file), start: 0, end: 0, duration: 0, volume: 1 };
      const probe = document.createElement('video'); probe.preload = 'metadata'; probe.src = clip.url;
      probe.onloadedmetadata = () => { clip.duration = probe.duration; clip.end = probe.duration; render(); };
      clips.push(clip);
    });
    setError(''); render(); updatePreview();
  }

  input.addEventListener('change', (e) => addFiles(e.target.files));
  ['dragenter','dragover'].forEach((event) => drop.addEventListener(event, (e) => { e.preventDefault(); drop.classList.add('dragging'); }));
  ['dragleave','drop'].forEach((event) => drop.addEventListener(event, (e) => { e.preventDefault(); drop.classList.remove('dragging'); }));
  drop.addEventListener('drop', (e) => addFiles(e.dataTransfer.files));

  exportBtn.addEventListener('click', async () => {
    if (clips.length < 2 || clips.length > 3) return;
    setError(''); exportBtn.disabled = true; exportBtn.textContent = 'Exporting…'; status.textContent = 'Encoding…';
    const form = new FormData(); clips.forEach((clip) => form.append('files', clip.file));
    form.append('clip_specs', JSON.stringify(clips.map((clip) => ({ start: clip.start, end: clip.end || clip.duration, volume: clip.volume }))));
    form.append('profile', profile.value); form.append('layout', layout.value); form.append('fps', fps.value);
    try {
      const response = await fetch('/api/merge/export', { method: 'POST', body: form });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Export failed');
      output.hidden = false; outputVideo.src = data.file_url; download.href = data.file_url; status.textContent = 'Export complete';
      output.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } catch (err) { setError(err.message); status.textContent = 'Export failed'; }
    finally { exportBtn.disabled = clips.length < 2; exportBtn.textContent = 'Export TikTok MP4 →'; }
  });
})();
