import { pcmToWav, waveformLevels } from "./audio.js";

async function checkedFetch(url, options) {
  let response;
  try { response = await fetch(url, options); }
  catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Couldn’t reach the server. Check your connection and try again.");
  }
  if (response.ok) return response;
  if (response.status === 409) throw new Error("This model is working on another request. Please try again in a moment.");
  if (response.status === 413) throw new Error("That file is too large. Choose an audio file smaller than 64 MiB.");
  if (response.status >= 500) throw new Error("The server couldn’t finish this request. Please try again, or check that both models are running.");
  let detail;
  try { detail = (await response.json()).detail; } catch { /* A server can return an empty error body. */ }
  throw new Error(typeof detail === "string" ? detail : "Please check your input and try again.");
}

export async function generateSpeech(text, instruction, signal) {
  const body = new URLSearchParams({ text, instruction });
  const response = await checkedFetch("/v1/audio/speech", { method: "POST", body, signal });
  if (response.headers.get("X-Sample-Format") !== "s16le") throw new Error("The server returned an unsupported audio format.");
  const sampleRate = Number(response.headers.get("X-Sample-Rate"));
  const pcm = await response.arrayBuffer();
  return { blob: pcmToWav(pcm, sampleRate), duration: pcm.byteLength / (sampleRate * 2), levels: waveformLevels(pcm) };
}

export async function transcribeAudio(file, signal) {
  const body = new FormData(); body.append("file", file);
  const response = await checkedFetch("/v1/audio/transcriptions", { method: "POST", body, signal });
  const result = await response.json();
  if (typeof result.text !== "string") throw new Error("The server returned an unreadable transcript. Please try again.");
  return result;
}

export async function getSpeechCapabilities() {
  const response = await checkedFetch("/v1/audio/speech/capabilities", {
    cache: "no-store", signal: AbortSignal.timeout(5000),
  });
  return response.json();
}

export async function getTranscriptionCapabilities() {
  const response = await checkedFetch("/v1/audio/transcriptions/capabilities", {
    cache: "no-store", signal: AbortSignal.timeout(5000),
  });
  return response.json();
}
