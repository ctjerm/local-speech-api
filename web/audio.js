export function pcmToWav(pcm, sampleRate) {
  if (!pcm.byteLength || pcm.byteLength % 2 || !Number.isInteger(sampleRate) || sampleRate < 8000 || sampleRate > 192000) {
    throw new Error("The server returned incomplete or unsupported audio. Please try again.");
  }
  const header = new ArrayBuffer(44);
  const view = new DataView(header);
  const write = (offset, value) => [...value].forEach((character, i) => view.setUint8(offset + i, character.charCodeAt(0)));
  write(0, "RIFF"); view.setUint32(4, 36 + pcm.byteLength, true); write(8, "WAVE");
  write(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); write(36, "data"); view.setUint32(40, pcm.byteLength, true);
  return new Blob([header, pcm], { type: "audio/wav" });
}

export function waveformLevels(pcm, count = 72) {
  const samples = new DataView(pcm);
  const length = pcm.byteLength / 2;
  return Array.from({ length: count }, (_, bar) => {
    const start = Math.floor(bar * length / count);
    const end = Math.max(start + 1, Math.floor((bar + 1) * length / count));
    let peak = 0;
    for (let i = start; i < end && i < length; i++) peak = Math.max(peak, Math.abs(samples.getInt16(i * 2, true)) / 32768);
    return peak;
  });
}

export function drawWaveform(canvas, levels) {
  const width = canvas.clientWidth;
  if (!width || !levels.length) return;
  const height = canvas.clientHeight;
  const scale = window.devicePixelRatio || 1;
  canvas.width = width * scale; canvas.height = height * scale;
  const context = canvas.getContext("2d");
  context.scale(scale, scale);
  const step = width / levels.length;
  const maximum = Math.max(...levels, 0.01);
  levels.forEach((value, i) => {
    const barHeight = Math.max(3, value / maximum * (height - 12));
    context.fillStyle = i % 9 < 5 ? "#b9c9a7" : "#d4a47c";
    context.beginPath(); context.roundRect(i * step, (height - barHeight) / 2, Math.max(2, step * 0.48), barHeight, 3); context.fill();
  });
}
