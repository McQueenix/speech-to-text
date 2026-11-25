// ---------------------------------------------------------------------------
// Speech to Text — frontend
//   * Streams mic audio (16 kHz PCM) to the backend over a WebSocket
//   * Shows interim (grey) and final (black) text as the user speaks
//   * Dashboard: list / search / create / edit / delete / read aloud (TTS)
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 10;

const ui = {
  recordBtn: $("recordBtn"), recordLabel: $("recordLabel"), timer: $("timer"),
  meterBar: $("meterBar"), language: $("language"),
  finalText: $("finalText"), interimText: $("interimText"), placeholder: $("placeholder"),
  message: $("message"), engineStatus: $("engineStatus"),
  list: $("list"), search: $("search"), totalCount: $("totalCount"),
  prevBtn: $("prevBtn"), nextBtn: $("nextBtn"), pageInfo: $("pageInfo"), newBtn: $("newBtn"),
  dialog: $("editDialog"), dialogTitle: $("dialogTitle"), editForm: $("editForm"),
  editTitle: $("editTitle"), editText: $("editText"), editLanguage: $("editLanguage"),
  cancelEdit: $("cancelEdit"),
};

// ------------------------------- helpers ----------------------------------
function setMessage(text, isError = false) {
  ui.message.textContent = text || "";
  ui.message.classList.toggle("error", isError);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function formatDate(iso) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res.json();
}

// ------------------------------ recording ---------------------------------
const rec = { ws: null, ctx: null, stream: null, node: null, timerId: null, startedAt: 0, finals: [], active: false };

function resetLiveBox() {
  rec.finals = [];
  ui.finalText.textContent = "";
  ui.interimText.textContent = "";
  ui.placeholder.hidden = false;
}

function renderLive(interim = "") {
  ui.finalText.textContent = rec.finals.join(" ") + (rec.finals.length && interim ? " " : "");
  ui.interimText.textContent = interim;
  ui.placeholder.hidden = Boolean(rec.finals.length || interim);
}

function setRecordingUi(state) {
  // state: "idle" | "connecting" | "recording" | "saving"
  ui.recordBtn.classList.toggle("recording", state === "recording");
  ui.recordBtn.disabled = state === "connecting" || state === "saving";
  ui.recordLabel.textContent = {
    idle: "Start speaking", connecting: "Connecting…", recording: "Stop & save", saving: "Saving…",
  }[state];
  ui.language.disabled = state !== "idle";
}

async function startRecording() {
  resetLiveBox();
  setMessage("");
  setRecordingUi("connecting");

  try {
    rec.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (err) {
    setRecordingUi("idle");
    setMessage("Microphone permission is needed to transcribe. " + err.message, true);
    return;
  }

  const proto = location.protocol === "https:" ? "wss" : "ws";
  const lang = encodeURIComponent(ui.language.value);
  rec.ws = new WebSocket(`${proto}://${location.host}/ws/transcribe?lang=${lang}`);
  rec.ws.binaryType = "arraybuffer";

  rec.ws.onmessage = async (event) => {
    const msg = JSON.parse(event.data);
    switch (msg.type) {
      case "ready":
        await startAudioPipeline();
        rec.active = true;
        setRecordingUi("recording");
        setMessage("Listening… speak in Hindi, English or both.");
        break;
      case "interim":
        renderLive(msg.text);
        break;
      case "final":
        rec.finals.push(msg.text.trim());
        renderLive("");
        break;
      case "saved":
        setMessage("Saved to history ✓");
        loadHistory(0);
        break;
      case "empty":
        setMessage(msg.message);
        break;
      case "error":
        setMessage(msg.message, true);
        break;
    }
  };

  rec.ws.onclose = () => {
    stopAudioPipeline();
    rec.active = false;
    setRecordingUi("idle");
  };
  rec.ws.onerror = () => setMessage("Lost connection to the server.", true);
}

async function startAudioPipeline() {
  rec.ctx = new AudioContext();
  await rec.ctx.audioWorklet.addModule("/static/pcm-worklet.js");
  const source = rec.ctx.createMediaStreamSource(rec.stream);
  rec.node = new AudioWorkletNode(rec.ctx, "pcm-downsampler");
  rec.node.port.onmessage = ({ data }) => {
    if (rec.ws && rec.ws.readyState === WebSocket.OPEN) rec.ws.send(data);
    updateMeter(new Int16Array(data));
  };
  source.connect(rec.node);
  // Not connected to destination → no echo of your own voice.

  rec.startedAt = Date.now();
  rec.timerId = setInterval(() => {
    const s = Math.floor((Date.now() - rec.startedAt) / 1000);
    ui.timer.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }, 250);
}

function updateMeter(samples) {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  const rms = Math.sqrt(sum / samples.length) / 32768;
  ui.meterBar.style.width = Math.min(100, rms * 400) + "%";
}

function stopAudioPipeline() {
  clearInterval(rec.timerId);
  ui.meterBar.style.width = "0";
  if (rec.node) { rec.node.port.onmessage = null; rec.node.disconnect(); rec.node = null; }
  if (rec.ctx) { rec.ctx.close(); rec.ctx = null; }
  if (rec.stream) { rec.stream.getTracks().forEach((t) => t.stop()); rec.stream = null; }
}

function stopRecording() {
  stopAudioPipeline();
  setRecordingUi("saving");
  if (rec.ws && rec.ws.readyState === WebSocket.OPEN) {
    rec.ws.send(JSON.stringify({ type: "stop" }));
  } else {
    setRecordingUi("idle");
  }
}

ui.recordBtn.addEventListener("click", () => (rec.active ? stopRecording() : startRecording()));

// --------------------------- text to speech -------------------------------
// Uses the browser's built-in speech synthesis (no API key, works offline in Chrome).
function speak(text, button) {
  if (!("speechSynthesis" in window)) { setMessage("Text-to-speech isn't supported in this browser.", true); return; }
  if (speechSynthesis.speaking) { speechSynthesis.cancel(); button.textContent = "▶ Play"; return; }
  const utter = new SpeechSynthesisUtterance(text);
  const hasDevanagari = /[ऀ-ॿ]/.test(text);
  utter.lang = hasDevanagari ? "hi-IN" : "en-IN";
  const voice = speechSynthesis.getVoices().find((v) => v.lang === utter.lang);
  if (voice) utter.voice = voice;
  utter.onend = () => (button.textContent = "▶ Play");
  button.textContent = "■ Stop";
  speechSynthesis.speak(utter);
}

// ------------------------------ history -----------------------------------
const store = { skip: 0, total: 0, items: [], q: "" };

async function loadHistory(skip = store.skip) {
  const params = new URLSearchParams({ skip, limit: PAGE_SIZE });
  if (store.q) params.set("q", store.q);
  try {
    const page = await api(`/api/transcriptions?${params}`);
    Object.assign(store, { skip: page.skip, total: page.total, items: page.items });
    renderHistory();
  } catch (err) {
    ui.list.innerHTML = `<p class="empty">Couldn't load history: ${escapeHtml(err.message)}</p>`;
  }
}

function renderHistory() {
  ui.totalCount.textContent = store.total ? `(${store.total})` : "";
  if (!store.items.length) {
    ui.list.innerHTML = `<p class="empty">${store.q ? "No matches." : "No transcriptions yet — record one!"}</p>`;
  } else {
    ui.list.innerHTML = store.items.map((t) => `
      <article class="item" data-id="${t.id}">
        <div class="item-head">
          <span class="item-title">${escapeHtml(t.title)}<span class="tag">${escapeHtml(t.source)}</span><span class="tag">${escapeHtml(t.language)}</span></span>
          <span class="item-meta">${formatDate(t.created_at)}${t.duration_seconds ? " · " + Math.round(t.duration_seconds) + "s" : ""}</span>
        </div>
        <p class="item-text">${escapeHtml(t.text)}</p>
        <div class="item-actions">
          <button data-action="play">▶ Play</button>
          <button data-action="copy">Copy</button>
          <button data-action="edit">Edit</button>
          <button data-action="delete" class="del">Delete</button>
        </div>
      </article>`).join("");
  }
  const page = Math.floor(store.skip / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(store.total / PAGE_SIZE));
  ui.pageInfo.textContent = `Page ${page} of ${pages}`;
  ui.prevBtn.disabled = store.skip === 0;
  ui.nextBtn.disabled = store.skip + PAGE_SIZE >= store.total;
}

ui.list.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const id = Number(btn.closest(".item").dataset.id);
  const item = store.items.find((t) => t.id === id);
  switch (btn.dataset.action) {
    case "play": speak(item.text, btn); break;
    case "copy":
      await navigator.clipboard.writeText(item.text);
      btn.textContent = "Copied ✓"; setTimeout(() => (btn.textContent = "Copy"), 1200);
      break;
    case "edit": openDialog(item); break;
    case "delete":
      if (!confirm(`Delete “${item.title}”? This can't be undone.`)) return;
      await api(`/api/transcriptions/${id}`, { method: "DELETE" });
      const lastOnPage = store.items.length === 1 && store.skip > 0;
      loadHistory(lastOnPage ? store.skip - PAGE_SIZE : store.skip);
      break;
  }
});

let searchTimer;
ui.search.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { store.q = ui.search.value.trim(); loadHistory(0); }, 300);
});
ui.prevBtn.addEventListener("click", () => loadHistory(Math.max(0, store.skip - PAGE_SIZE)));
ui.nextBtn.addEventListener("click", () => loadHistory(store.skip + PAGE_SIZE));

// --------------------------- create / edit --------------------------------
let editingId = null;

function openDialog(item = null) {
  editingId = item ? item.id : null;
  ui.dialogTitle.textContent = item ? "Edit transcription" : "New transcription";
  ui.editTitle.value = item ? item.title : "";
  ui.editText.value = item ? item.text : "";
  ui.editLanguage.value = item ? item.language : "auto";
  ui.dialog.showModal();
}

ui.newBtn.addEventListener("click", () => openDialog());
ui.cancelEdit.addEventListener("click", () => ui.dialog.close());

ui.editForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = JSON.stringify({
    title: ui.editTitle.value.trim(),
    text: ui.editText.value.trim(),
    language: ui.editLanguage.value.trim() || "auto",
  });
  try {
    if (editingId) await api(`/api/transcriptions/${editingId}`, { method: "PUT", body });
    else await api("/api/transcriptions", { method: "POST", body });
    ui.dialog.close();
    loadHistory(editingId ? store.skip : 0);
  } catch (err) {
    alert("Couldn't save: " + err.message);
  }
});

// -------------------------------- init ------------------------------------
(async function init() {
  try {
    const h = await api("/api/health");
    ui.engineStatus.textContent = h.speech_engine_configured ? `● ${h.speech_engine}` : "Speech engine not configured";
    ui.engineStatus.classList.add(h.speech_engine_configured ? "ok" : "bad");
  } catch (_) {
    ui.engineStatus.textContent = "Server offline";
    ui.engineStatus.classList.add("bad");
  }
  if ("speechSynthesis" in window) speechSynthesis.getVoices(); // warm up voice list
  loadHistory(0);
})();
