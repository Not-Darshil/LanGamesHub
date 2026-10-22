/**
 * Geometry for the standard 15×15 Ludo board. [row, col], origin top-left.
 * Absolute track square 0 is red's start square; the track runs clockwise.
 */
export type Color = "red" | "green" | "yellow" | "blue";
export type Cell = [number, number];

function run(from: Cell, dRow: number, dCol: number, count: number): Cell[] {
  return Array.from({ length: count }, (_, i) => [from[0] + dRow * i, from[1] + dCol * i] as Cell);
}

export const TRACK: Cell[] = [
  ...run([6, 1], 0, 1, 5),    // 0–4   red arm, rightwards
  ...run([5, 6], -1, 0, 6),   // 5–10  up the top arm
  [0, 7],                     // 11
  ...run([0, 8], 1, 0, 6),    // 12–17 down (green start at 13)
  ...run([6, 9], 0, 1, 6),    // 18–23 right arm
  [7, 14],                    // 24
  ...run([8, 14], 0, -1, 6),  // 25–30 back (yellow start at 26)
  ...run([9, 8], 1, 0, 6),    // 31–36 down the bottom arm
  [14, 7],                    // 37
  ...run([14, 6], -1, 0, 6),  // 38–43 up (blue start at 39)
  ...run([8, 5], 0, -1, 6),   // 44–49 left arm
  [7, 0],                     // 50
  [6, 0],                     // 51
];

export const HOME_COLUMN: Record<Color, Cell[]> = {
  red: run([7, 1], 0, 1, 5),
  green: run([1, 7], 1, 0, 5),
  yellow: run([7, 13], 0, -1, 5),
  blue: run([13, 7], -1, 0, 5),
};

export const YARD_SLOTS: Record<Color, Cell[]> = {
  red: [[2, 2], [2, 3], [3, 2], [3, 3]],
  green: [[2, 11], [2, 12], [3, 11], [3, 12]],
  yellow: [[11, 11], [11, 12], [12, 11], [12, 12]],
  blue: [[11, 2], [11, 3], [12, 2], [12, 3]],
};

export const YARD_AREA: Record<Color, { row: number; col: number }> = {
  red: { row: 0, col: 0 }, green: { row: 0, col: 9 }, yellow: { row: 9, col: 9 }, blue: { row: 9, col: 0 },
};

export const CENTER: Cell = [7, 7];

/** Where a token with this progress is drawn. */
export function tokenCell(color: Color, start: number, progress: number, index: number): Cell {
  if (progress < 0) return YARD_SLOTS[color][index] ?? YARD_SLOTS[color][0]!;
  if (progress <= 50) return TRACK[(start + progress) % 52]!;
  if (progress <= 55) return HOME_COLUMN[color][progress - 51]!;
  return CENTER;
}

/** A continuous board position [row, col] in cell units; a cell's centre is r + 0.5, c + 0.5. */
export type Point = [number, number];

export const COLORS: Color[] = ["red", "green", "yellow", "blue"];

/** Degrees to rotate a rightward arrow on each colour's start square (direction of travel). */
export const START_ARROW: Record<Color, number> = { red: 0, green: 90, yellow: 180, blue: 270 };

/** Token slot centres inside each yard, spread out across the yard's inner panel. */
export const SLOT_POINTS: Record<Color, Point[]> = Object.fromEntries(
  COLORS.map((color) => {
    const { row, col } = YARD_AREA[color];
    return [color, [[row + 2, col + 2], [row + 2, col + 4], [row + 4, col + 2], [row + 4, col + 4]]];
  }),
) as Record<Color, Point[]>;

/** Where finished tokens rest: a row along the base of their colour's centre triangle. */
export function finishPoint(color: Color, index: number): Point {
  const along = 6.9 + index * 0.4;
  switch (color) {
    case "red": return [along, 6.45];
    case "green": return [6.45, along];
    case "yellow": return [along, 8.55];
    case "blue": return [8.55, along];
  }
}

/** Centre point at which a token with this progress is drawn. */
export function tokenPoint(color: Color, start: number, progress: number, index: number): Point {
  if (progress < 0) return SLOT_POINTS[color][index] ?? SLOT_POINTS[color][0]!;
  if (progress >= 56) return finishPoint(color, index);
  const [r, c] = tokenCell(color, start, progress, index);
  return [r + 0.5, c + 0.5];
}
