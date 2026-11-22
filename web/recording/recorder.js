import { pcmToWav } from "../audio.js";

export function recordingSupport() {
  if (!window.isSecureContext) return "Microphone recording needs a trusted HTTPS connection. Use the secure address below, or localhost on the server PC.";
  if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext || !window.AudioWorkletNode) {
    return "This browser cannot record audio here. Try a current Chrome, Edge, Firefox, or Safari browser, or upload a recording.";
  }
  return "";
}

export function recordingError(error) {
  const messages = {
    NotAllowedError: "Microphone access was denied. Allow the microphone in this site’s browser permissions, then try again.",
    NotFoundError: "No microphone was found. Connect a microphone and try again.",
    NotReadableError: "The microphone could not start. Check your device settings and whether another app is using it.",
    AbortError: "Recording cancelled.",
  };
  return messages[error.name] || error.message || "Could not record audio. Please try again.";
}

export async function startCapture({ signal, onProgress, onLimit, onInterrupted }) {
  signal.throwIfAborted();
  const context = new AudioContext({ sampleRate: 16000 });
  let stream, source, node;
  let chunks = [];
  let frames = 0;
  let finished = false;
  let resolveDone;
  const done = new Promise((resolve) => { resolveDone = resolve; });
  const cleanup = () => {
    stream?.getTracks().forEach((track) => track.stop());
    source?.disconnect();
    node?.disconnect();
    if (context.state !== "closed") context.close().catch(() => {});
  };
  const abort = () => { cleanup(); chunks = []; resolveDone(); };
  signal.addEventListener("abort", abort, { once: true });
  try {
    await context.resume();
    signal.throwIfAborted();
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }, video: false });
    // Permission prompts cannot be aborted. Release a stream granted after Cancel immediately.
    signal.throwIfAborted();
    await context.audioWorklet.addModule(new URL("./pcm-worklet.js", import.meta.url));
    signal.throwIfAborted();
    const maxFrames = Math.min(32_000_000, context.sampleRate * 1800);
    node = new AudioWorkletNode(context, "pcm-capture", {
      channelCount: 1, channelCountMode: "explicit", processorOptions: { maxFrames },
    });
    node.port.onmessage = ({ data }) => {
      if (signal.aborted) return;
      if (data.type === "pcm") {
        chunks.push(data.bytes);
        frames = data.frames;
        onProgress(frames / context.sampleRate, maxFrames / context.sampleRate);
      } else if (data.type === "done") {
        finished = true;
        resolveDone();
        if (frames >= maxFrames) onLimit();
      }
    };
    node.onprocessorerror = () => onInterrupted(new Error("Audio capture stopped unexpectedly. Please record again."));
    stream.getAudioTracks().forEach((track) => track.addEventListener("ended", () => onInterrupted(new Error("The microphone disconnected. Please reconnect it and record again.")), { once: true }));
    source = context.createMediaStreamSource(stream);
    source.connect(node);
    node.connect(context.destination);
    return {
      async finish() {
        stream.getTracks().forEach((track) => track.stop());
        let timeout;
        try {
          if (!finished) node.port.postMessage("finish");
          await Promise.race([done, new Promise((_, reject) => {
            timeout = setTimeout(() => reject(new Error("Recording could not finish. Please try again.")), 3000);
          })]);
          signal.throwIfAborted();
          if (!frames) throw new Error("No audio was captured. Record for a moment before stopping.");
          const pcm = new Uint8Array(frames * 2);
          let offset = 0;
          for (const chunk of chunks) { pcm.set(new Uint8Array(chunk), offset); offset += chunk.byteLength; }
          return pcmToWav(pcm.buffer, context.sampleRate);
        } finally {
          clearTimeout(timeout);
          signal.removeEventListener("abort", abort);
          cleanup();
          chunks = [];
        }
      },
    };
  } catch (error) {
    signal.removeEventListener("abort", abort);
    cleanup();
    throw error;
  }
}
