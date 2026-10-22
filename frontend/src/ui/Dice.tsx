import { useEffect, useRef, useState } from "react";

/** Pip layout per face on a 3×3 grid (cells 1–9, row-major). */
const PIPS: Record<number, number[]> = {
  1: [5], 2: [3, 7], 3: [3, 5, 7], 4: [1, 3, 7, 9], 5: [1, 3, 5, 7, 9], 6: [1, 3, 4, 6, 7, 9],
};
// Faces: front 1, right 2, top 3, bottom 4, left 5, back 6 (opposites sum to 7).
const FACES: { value: number; transform: string }[] = [
  { value: 1, transform: "rotateY(0deg)" },
  { value: 2, transform: "rotateY(90deg)" },
  { value: 3, transform: "rotateX(90deg)" },
  { value: 4, transform: "rotateX(-90deg)" },
  { value: 5, transform: "rotateY(-90deg)" },
  { value: 6, transform: "rotateY(180deg)" },
];
// Cube rotation that brings each value to the front.
const SHOW: Record<number, [number, number]> = {
  1: [0, 0], 2: [0, -90], 3: [-90, 0], 4: [90, 0], 5: [0, 90], 6: [0, 180],
};

/**
 * A 3D die. Changing `rollKey` (e.g. a game version) with a value tumbles it onto that
 * value; the same key keeps it still, so re-renders never re-roll.
 */
export function Die({ value, rollKey, size = 64, onSettled }: {
  value: number | null; rollKey?: string | number; size?: number; onSettled?: () => void;
}) {
  const [spins, setSpins] = useState(0);
  const [rolling, setRolling] = useState(false);
  const lastKey = useRef(rollKey);
  const settled = useRef(onSettled);
  settled.current = onSettled;

  useEffect(() => {
    if (rollKey === lastKey.current) return;
    lastKey.current = rollKey;
    if (value == null) return;
    setSpins((s) => s + 1);
    setRolling(true);
    const timer = window.setTimeout(() => {
      setRolling(false);
      settled.current?.();
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [rollKey, value]);

  const [x, y] = SHOW[value ?? 1] ?? [0, 0];
  const half = size / 2;
  const transform = `translateZ(-${half}px) rotateX(${x - 18 + spins * 720}deg) rotateY(${y + 22 + spins * 360}deg)`;
  return (
    <div>
      <div className={`die-scene${rolling ? " rolling" : ""}`} style={{ ["--die" as string]: `${size}px` }}
        aria-label={value ? `Die showing ${value}` : "Die"} role="img">
        <div className="die" style={{ transform }}>
          {FACES.map((f) => (
            <div key={f.value} className={`die-face f${f.value}`}
              style={{ transform: `${f.transform} translateZ(${half}px)` }}>
              {Array.from({ length: 9 }, (_, i) => (
                <span key={i} style={{ display: "grid" }}>{PIPS[f.value]!.includes(i + 1) && <i />}</span>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="die-shadow" />
    </div>
  );
}
