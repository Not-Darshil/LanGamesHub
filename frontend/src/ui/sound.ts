/**
 * Tiny synthesized sound effects (Web Audio, no audio files). Muted state is a per-browser
 * preference. Browsers only allow audio after a user gesture, so early sounds are dropped.
 */
export type Sound =
  | "move" | "capture" | "check" | "turn" | "dice" | "card" | "win" | "lose" | "tick" | "error"
  | "pop" | "splash" | "boom" | "ladder" | "snake" | "notify";

const KEY = "lgh-sound-muted";
let muted = readMuted();
let hostMuted = false; // the host silenced this browser (overrides the player's choice)
let ctx: AudioContext | null = null;
const listeners = new Set<() => void>();

function readMuted(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function isMuted(): boolean {
  return muted;
}

export function setMuted(value: boolean): void {
  muted = value;
  try {
    window.localStorage.setItem(KEY, value ? "1" : "0");
  } catch {
    /* storage unavailable: keep the in-memory setting */
  }
  listeners.forEach((l) => l());
}

export function isHostMuted(): boolean {
  return hostMuted;
}

export function setHostMuted(value: boolean): void {
  if (hostMuted === value) return;
  hostMuted = value;
  listeners.forEach((l) => l());
}

export function subscribeMuted(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function audio(): AudioContext | null {
  if (ctx) return ctx;
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  try {
    ctx = new Ctor();
  } catch {
    return null;
  }
  return ctx;
}

// Unlock audio on the first interaction.
if (typeof window !== "undefined") {
  const unlock = () => {
    const a = audio();
    if (a && a.state === "suspended") void a.resume();
  };
  window.addEventListener("pointerdown", unlock, { passive: true });
  window.addEventListener("keydown", unlock);
}

interface Tone {
  freq: number; to?: number; type?: OscillatorType; dur?: number; vol?: number; at?: number; attack?: number;
}

function tone(a: AudioContext, { freq, to, type = "sine", dur = 0.12, vol = 0.12, at = 0, attack = 0.005 }: Tone) {
  const t = a.currentTime + at;
  const osc = a.createOscillator();
  const gain = a.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t);
  if (to) osc.frequency.exponentialRampToValueAtTime(to, t + dur);
  gain.gain.setValueAtTime(0.0001, t);
  gain.gain.exponentialRampToValueAtTime(vol, t + attack);
  gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  osc.connect(gain).connect(a.destination);
  osc.start(t);
  osc.stop(t + dur + 0.02);
}

function noise(a: AudioContext, { dur = 0.08, vol = 0.12, at = 0, freq = 1800, q = 1.2, type = "bandpass" as BiquadFilterType } = {}) {
  const t = a.currentTime + at;
  const length = Math.max(1, Math.floor(a.sampleRate * dur));
  const buffer = a.createBuffer(1, length, a.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < length; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / length);
  const src = a.createBufferSource();
  src.buffer = buffer;
  const filter = a.createBiquadFilter();
  filter.type = type;
  filter.frequency.value = freq;
  filter.Q.value = q;
  const gain = a.createGain();
  gain.gain.setValueAtTime(vol, t);
  gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  src.connect(filter).connect(gain).connect(a.destination);
  src.start(t);
}

export function play(sound: Sound): void {
  if (muted || hostMuted) return;
  const a = audio();
  if (!a || a.state !== "running") return;
  try {
    switch (sound) {
      case "move":
        noise(a, { dur: 0.05, vol: 0.25, freq: 900, q: 2 });
        tone(a, { freq: 340, to: 200, type: "triangle", dur: 0.08, vol: 0.12 });
        break;
      case "capture":
        noise(a, { dur: 0.09, vol: 0.35, freq: 700, q: 1.5 });
        tone(a, { freq: 260, to: 120, type: "triangle", dur: 0.14, vol: 0.16 });
        break;
      case "check":
        tone(a, { freq: 880, type: "square", dur: 0.08, vol: 0.05 });
        tone(a, { freq: 660, type: "square", dur: 0.12, vol: 0.05, at: 0.09 });
        break;
      case "turn":
      case "notify":
        tone(a, { freq: 660, type: "sine", dur: 0.18, vol: 0.09 });
        tone(a, { freq: 990, type: "sine", dur: 0.28, vol: 0.08, at: 0.1 });
        break;
      case "dice":
        for (let i = 0; i < 5; i++) noise(a, { dur: 0.035, vol: 0.22, freq: 2400 - i * 250, q: 3, at: i * 0.07 + Math.random() * 0.02 });
        break;
      case "card":
        noise(a, { dur: 0.12, vol: 0.18, freq: 3200, q: 0.8, type: "highpass" });
        break;
      case "pop":
        tone(a, { freq: 520, to: 880, type: "sine", dur: 0.09, vol: 0.1 });
        break;
      case "win":
        [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => tone(a, { freq: f, type: "triangle", dur: 0.35, vol: 0.1, at: i * 0.11 }));
        break;
      case "lose":
        [392, 349.23, 311.13, 261.63].forEach((f, i) => tone(a, { freq: f, type: "triangle", dur: 0.32, vol: 0.08, at: i * 0.13 }));
        break;
      case "tick":
        tone(a, { freq: 1400, type: "square", dur: 0.03, vol: 0.035 });
        break;
      case "error":
        tone(a, { freq: 180, type: "sawtooth", dur: 0.16, vol: 0.05 });
        break;
      case "splash":
        noise(a, { dur: 0.35, vol: 0.25, freq: 1200, q: 0.6, type: "lowpass" });
        break;
      case "boom":
        noise(a, { dur: 0.5, vol: 0.5, freq: 300, q: 0.7, type: "lowpass" });
        tone(a, { freq: 110, to: 40, type: "sine", dur: 0.45, vol: 0.25 });
        break;
      case "ladder":
        [523.25, 659.25, 783.99, 987.77, 1174.66].forEach((f, i) => tone(a, { freq: f, type: "sine", dur: 0.14, vol: 0.07, at: i * 0.06 }));
        break;
      case "snake":
        tone(a, { freq: 700, to: 140, type: "sawtooth", dur: 0.5, vol: 0.05 });
        break;
    }
  } catch {
    /* audio is best-effort */
  }
}
