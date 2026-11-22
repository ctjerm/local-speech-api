import { recordingError, recordingSupport, startCapture } from "./recorder.js";

const $ = (id) => document.getElementById(id);
const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

export function mountRecorder({ onBusy, onRecording, pausePlayback }) {
  let session = null;
  let blocked = false;
  const unsupported = recordingSupport();
  const message = (text, error = false) => {
    $("microphone-status").textContent = text;
    $("microphone-status").dataset.kind = error ? "error" : "";
  };
  function refresh() {
    $("microphone-button").disabled = Boolean(unsupported) || blocked || (session && session.phase !== "recording");
    $("microphone-button").setAttribute("aria-pressed", String(session?.phase === "recording"));
    $("microphone-label").textContent = session?.phase === "recording" ? "Stop recording" : session ? "Preparing…" : "Record microphone";
    $("microphone-box").classList.toggle("is-recording", session?.phase === "recording");
    $("cancel-recording").hidden = !session;
    onBusy(Boolean(session));
  }
  function cancel() {
    if (!session) return;
    session.controller.abort();
    session = null;
    message("Recording cancelled.");
    refresh();
  }
  async function finish(current) {
    if (session !== current || current.phase !== "recording") return;
    current.phase = "saving";
    refresh();
    message("Preparing your recording…");
    try {
      const blob = await current.capture.finish();
      if (session !== current) return;
      session = null;
      refresh();
      const name = `microphone-${new Date().toISOString().replace(/[:.]/g, "-")}.wav`;
      onRecording(new File([blob], name, { type: "audio/wav" }));
      message("Recording ready. Listen below, then choose Transcribe audio.");
    } catch (error) {
      if (session === current) { session = null; refresh(); message(recordingError(error), true); }
    }
  }
  $("microphone-button").addEventListener("click", async () => {
    if (session) { finish(session); return; }
    if (blocked || unsupported) return;
    const current = { controller: new AbortController(), phase: "starting", capture: null };
    session = current;
    pausePlayback();
    refresh();
    message("Allow microphone access in your browser when prompted.");
    try {
      current.capture = await startCapture({
        signal: current.controller.signal,
        onProgress: (seconds, limit) => {
          if (session === current && current.phase === "recording") {
            $("recording-timer").textContent = clock(seconds);
            $("recording-limit").textContent = `Up to ${Math.floor(limit / 60)} minutes`;
          }
        },
        onLimit: () => finish(current),
        onInterrupted: (error) => {
          if (session === current) { cancel(); message(recordingError(error), true); }
        },
      });
      if (session !== current) return;
      current.phase = "recording";
      $("recording-timer").textContent = "0:00";
      message("Microphone is recording. Stop when you’re ready.");
      refresh();
    } catch (error) {
      if (session === current) { session = null; refresh(); message(recordingError(error), true); }
    }
  });
  $("cancel-recording").addEventListener("click", cancel);
  window.addEventListener("pagehide", cancel);
  message(unsupported || "Record your voice, then preview and transcribe it.");
  if (!window.isSecureContext) {
    $("microphone-help").hidden = false;
    fetch("/site-config").then((response) => response.json()).then((config) => {
      if (!config.https_port) return;
      const url = new URL(location.href);
      url.protocol = "https:";
      url.port = config.https_port;
      $("secure-website").href = url.href;
      $("secure-website").hidden = false;
    }).catch(() => {});
  }
  refresh();
  return { setBlocked(value) { blocked = value; refresh(); } };
}
