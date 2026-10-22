/** Pure helpers for the Typing Race UI (mirrors backend app/games/typing_race.py). */

/** Characters the server lets a report run past the end of the passage. */
export const MAX_EXTRA_CHARS = 10;
/** How many wrong characters may pile up after the first mistake before input stops. */
export const MAX_WRONG_CHARS = 8;
/** Minimum gap between progress reports (at most 4 per second). */
export const SEND_GAP_MS = 250;

/** Length of the longest prefix of `typed` that matches `passage`. */
export function correctPrefix(typed: string, passage: string): number {
  const n = Math.min(typed.length, passage.length);
  let i = 0;
  while (i < n && typed[i] === passage[i]) i++;
  return i;
}

/** [start, end) of each word (runs of non-spaces) in the passage. */
export function wordRanges(passage: string): [number, number][] {
  const ranges: [number, number][] = [];
  const re = /\S+/g;
  for (let m = re.exec(passage); m; m = re.exec(passage)) ranges.push([m.index, m.index + m[0].length]);
  return ranges;
}

/** Index of the word being worked on: the one containing `pos` or the space right after it. */
export function currentWord(ranges: [number, number][], pos: number): number {
  return ranges.findIndex(([start, end]) => pos >= start && pos <= end);
}

/** Words per minute (five characters per word). */
export function wpm(chars: number, elapsedMs: number): number {
  if (chars <= 0 || elapsedMs <= 0) return 0;
  return Math.round(chars / 5 / (elapsedMs / 60_000));
}

export function ordinal(n: number): string {
  const tens = n % 100;
  const suffix = tens >= 10 && tens <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

export function medal(place: number): string {
  return ["🥇", "🥈", "🥉"][place - 1] ?? `#${place}`;
}

/** m:ss, rounding up so a clock never shows 0:00 while time remains. */
export function formatClock(ms: number): string {
  const seconds = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** A finishing time, e.g. "41.3s" or "1:05.2". */
export function formatDuration(ms: number): string {
  const tenths = Math.round(ms / 100);
  const minutes = Math.floor(tenths / 600);
  const rest = ((tenths % 600) / 10).toFixed(1);
  return minutes ? `${minutes}:${rest.padStart(4, "0")}` : `${rest}s`;
}
