import { generateSpeech, getSpeechCapabilities, getTranscriptionCapabilities, transcribeAudio } from "./api.js";
import { drawWaveform } from "./audio.js";
import { mountRecorder } from "./recording/controls.js";

const $ = (id) => document.getElementById(id);
const jobs = { speech: null, transcription: null };
const urls = new Map();
let recording = null;
let generated = null;
let microphoneBusy = false;
let microphone;
let voiceDirectionSupported = false;

function feedback(id, message, kind = "") {
  $(id).textContent = message;
  $(id).dataset.kind = kind;
}

function objectUrl(name, blob) {
  if (urls.has(name)) URL.revokeObjectURL(urls.get(name));
  const url = URL.createObjectURL(blob);
  urls.set(name, url);
  return url;
}

function duration(seconds) {
  const rounded = Math.max(0, Math.round(seconds));
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

function refreshControls() {
  const speaking = Boolean(jobs.speech);
  const transcribing = Boolean(jobs.transcription);
  $("generate-button").disabled = speaking || !$("speech-text").value.trim();
  $("transcribe-button").disabled = transcribing || microphoneBusy || !recording;
  $("speech-text").disabled = speaking;
  $("voice-direction").disabled = speaking;
  $("example-button").disabled = speaking;
  $("audio-file").disabled = transcribing || microphoneBusy;
  $("remove-file").disabled = transcribing || microphoneBusy;
  $("use-audio").disabled = transcribing || microphoneBusy;
  for (const [job, button, label, busyLabel] of [
    ["speech", "generate-button", "Generate speech", "Creating audio…"],
    ["transcription", "transcribe-button", "Transcribe audio", "Transcribing…"],
  ]) {
    const busy = Boolean(jobs[job]);
    $(button).classList.toggle("is-busy", busy);
    $(button).querySelector(".button-label").textContent = busy ? busyLabel : label;
    $(`cancel-${job}`).hidden = !busy;
    $(job === "speech" ? "speech-form" : "transcription-form").setAttribute("aria-busy", String(busy));
  }
}

function selectTab(name, focus = false) {
  for (const tab of document.querySelectorAll("[role=tab]")) {
    const selected = tab.dataset.panel === name;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    $(`${tab.dataset.panel}-panel`).hidden = !selected;
    if (selected && focus) tab.focus();
  }
  if (name === "speak" && generated) requestAnimationFrame(() => drawWaveform($("waveform"), generated.levels));
}

for (const tab of document.querySelectorAll("[role=tab]")) {
  tab.addEventListener("click", () => selectTab(tab.dataset.panel));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? "speak" : event.key === "End" ? "transcribe"
      : tab.dataset.panel === "speak" ? "transcribe" : "speak";
    selectTab(next, true);
  });
}

async function runJob(name, operation, onSuccess, workingMessage) {
  if (jobs[name]) return;
  const controller = new AbortController();
  jobs[name] = controller;
  microphone?.setBlocked(Boolean(jobs.transcription));
  refreshControls();
  const started = performance.now();
  const update = () => feedback(`${name}-status`, `${workingMessage} ${Math.floor((performance.now() - started) / 1000)}s elapsed.`);
  update();
  const timer = setInterval(update, 1000);
  try {
    const result = await operation(controller.signal);
    if (!controller.signal.aborted) onSuccess(result, (performance.now() - started) / 1000);
  } catch (error) {
    feedback(`${name}-status`, controller.signal.aborted
      ? name === "transcription" ? "Cancelled. The server may briefly finish processing before accepting another recording." : "Cancelled. Ready when you are."
      : error.message || "Something went wrong. Please try again.", controller.signal.aborted ? "" : "error");
  } finally {
    clearInterval(timer);
    jobs[name] = null;
    microphone?.setBlocked(Boolean(jobs.transcription));
    refreshControls();
  }
}

$("speech-text").addEventListener("input", () => {
  const count = Array.from($("speech-text").value).length;
  $("text-count").textContent = `${count.toLocaleString()} ${count === 1 ? "character" : "characters"}`;
  refreshControls();
});
$("example-button").addEventListener("click", () => {
  $("speech-text").value = "Hello, and welcome. Take a breath, settle in, and let’s make something worth listening to.";
  $("voice-direction").value = voiceDirectionSupported ? "A warm, clear narrator with a relaxed and friendly delivery." : "";
  $("speech-text").dispatchEvent(new Event("input"));
  $("speech-text").focus();
});

$("speech-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("speech-text").value.trim();
  const instruction = voiceDirectionSupported ? $("voice-direction").value.trim() : "";
  if (!text) return;
  runJob("speech", (signal) => generateSpeech(text, instruction, signal), (result, elapsed) => {
    generated = result;
    const url = objectUrl("speech", result.blob);
    $("speech-player").src = url;
    $("audio-download").href = url;
    $("audio-duration").textContent = duration(result.duration);
    $("audio-empty").hidden = true;
    $("audio-result").hidden = false;
    if (!$("speak-panel").hidden) drawWaveform($("waveform"), result.levels);
    feedback("speech-status", `Audio ready. Created ${duration(result.duration)} of speech in ${elapsed.toFixed(1)}s.`, "success");
  }, "Creating your audio.");
});

function chooseRecording(file) {
  if (jobs.transcription || microphoneBusy) return;
  if (file && file.size > 64 * 1024 * 1024) {
    $("audio-file").value = "";
    feedback("transcription-status", "That file is too large. Choose an audio file up to 64 MiB.", "error");
    return;
  }
  recording = file;
  $("audio-file").value = "";
  $("selected-file").hidden = !file;
  $("upload-player").hidden = !file;
  $("preview-note").hidden = true;
  $("upload-player").pause();
  $("upload-player").removeAttribute("src");
  $("upload-player").load();
  if (file) {
    $("file-name").textContent = file.name;
    $("file-size").textContent = file.size >= 1024 * 1024 ? `${(file.size / (1024 * 1024)).toFixed(1)} MiB` : `${Math.ceil(file.size / 1024)} KiB`;
    $("upload-player").src = objectUrl("upload", file);
  } else if (urls.has("upload")) {
    URL.revokeObjectURL(urls.get("upload"));
    urls.delete("upload");
  }
  feedback("transcription-status", file ? "Ready to transcribe. Your first request after startup may take a little longer." : "Choose a recording to get started.");
  refreshControls();
}

$("audio-file").addEventListener("change", (event) => {
  if (event.target.files[0]) chooseRecording(event.target.files[0]);
});
$("remove-file").addEventListener("click", () => chooseRecording(null));
$("upload-player").addEventListener("error", () => {
  if (recording) $("preview-note").hidden = false;
});
$("use-audio").addEventListener("click", () => {
  if (!generated || jobs.transcription || microphoneBusy) return;
  chooseRecording(new File([generated.blob], "generated-speech.wav", { type: "audio/wav" }));
  selectTab("transcribe", true);
});

const dropZone = $("drop-zone");
for (const name of ["dragenter", "dragover"]) dropZone.addEventListener(name, (event) => {
  event.preventDefault();
  if (!jobs.transcription && !microphoneBusy) dropZone.classList.add("drag-over");
});
for (const name of ["dragleave", "drop"]) dropZone.addEventListener(name, () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  if (event.dataTransfer.files[0]) chooseRecording(event.dataTransfer.files[0]);
});
// Prevent an accidental drop outside the picker from navigating away from ongoing work.
window.addEventListener("dragover", (event) => { if (event.dataTransfer.types.includes("Files")) event.preventDefault(); });
window.addEventListener("drop", (event) => { if (event.dataTransfer.types.includes("Files")) event.preventDefault(); });

$("transcription-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!recording || microphoneBusy) return;
  const file = recording;
  runJob("transcription", (signal) => transcribeAudio(file, signal), (result, elapsed) => {
    $("transcript-text").value = result.text;
    $("transcript-meta").textContent = `${duration(result.duration)} of audio · ${file.name}`;
    $("transcript-download").href = objectUrl("transcript", new Blob([result.text], { type: "text/plain;charset=utf-8" }));
    $("transcript-empty").hidden = true;
    $("transcript-result").hidden = false;
    $("copy-transcript").disabled = !result.text;
    $("copy-status").textContent = "";
    feedback("transcription-status", result.text ? `Transcript ready in ${elapsed.toFixed(1)}s.` : "No speech was detected in this recording.", "success");
  }, "Listening to your recording.");
});

for (const name of Object.keys(jobs)) $(`cancel-${name}`).addEventListener("click", () => jobs[name]?.abort());

$("copy-transcript").addEventListener("click", async () => {
  let copied = false;
  if (navigator.clipboard) {
    try { await navigator.clipboard.writeText($("transcript-text").value); copied = true; } catch { /* Fall back for local HTTP and browser permissions. */ }
  }
  if (!copied) {
    $("transcript-text").focus();
    $("transcript-text").select();
    try { copied = document.execCommand("copy"); } catch { /* Keep the text selected for manual copy. */ }
  }
  $("copy-status").textContent = copied ? "Copied to clipboard." : "Text selected. Use your device’s Copy command to copy it.";
});

new ResizeObserver(() => {
  if (generated && !$("speak-panel").hidden) drawWaveform($("waveform"), generated.levels);
}).observe($("waveform"));
window.addEventListener("pagehide", () => {
  for (const controller of Object.values(jobs)) controller?.abort();
  // bfcache can restore this document, so preserve its object URLs until it is discarded.
});
microphone = mountRecorder({
  onBusy(busy) { microphoneBusy = busy; refreshControls(); },
  onRecording: chooseRecording,
  pausePlayback() { $("speech-player").pause(); $("upload-player").pause(); },
});
refreshControls();
getSpeechCapabilities().then((capabilities) => {
  voiceDirectionSupported = capabilities.voice_direction === true;
  $("voice-options").hidden = !voiceDirectionSupported;
  const languages = Array.isArray(capabilities.languages) ? capabilities.languages : [];
  $("speech-languages").textContent = languages.join(" · ");
  $("speech-languages").hidden = languages.length === 0;
}).catch(() => {
  if (!jobs.speech && !generated) feedback("speech-status", "Voice options are unavailable. You can still generate speech.");
});
getTranscriptionCapabilities().then((capabilities) => {
  const languages = Array.isArray(capabilities.languages) ? capabilities.languages : [];
  const parts = [];
  if (capabilities.automatic_language_detection === true) parts.push("Automatic language detection");
  if (languages.length) parts.push(languages.length <= 3 ? languages.join(" · ") : `${languages.length} supported languages`);
  $("transcription-languages").textContent = parts.join(" · ");
  $("transcription-language-note").hidden = parts.length === 0;
}).catch(() => { /* Missing metadata must not prevent uploads or microphone recording. */ });
