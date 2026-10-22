import type { GameViewBase } from "../types";

/** Per-seat token colours shared by board games. */
export const SEAT_COLORS = ["#dc2626", "#2563eb", "#16a34a", "#d97706"];

/** A player's colour, stable for the whole match (participants are in seat order). */
export function seatColor(view: GameViewBase, playerId: string): string {
  const seat = Math.max(0, Object.keys(view.names).indexOf(playerId));
  return SEAT_COLORS[seat % SEAT_COLORS.length] ?? "#6b7280";
}
