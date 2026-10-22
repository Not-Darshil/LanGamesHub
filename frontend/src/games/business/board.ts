import type { GameViewBase } from "../../types";

export type Kind =
  | "start" | "city" | "fund" | "tax" | "transport" | "jail" | "utility" | "rest" | "chance" | "go_to_jail";
export type Phase = "roll" | "buy" | "end" | "debt" | "over";

export interface Square {
  index: number;
  kind: Kind;
  name: string;
  price?: number;
  mortgage?: number;
  unmortgage?: number;
  group?: string;
  group_name?: string;
  color?: string;
  rents?: number[];
  house_cost?: number;
}

export interface BizPlayer {
  id: string;
  cash: number;
  position: number;
  in_jail: boolean;
  jail_attempts: number;
  bankrupt: boolean;
  left: boolean;
  net_worth: number;
  properties: number;
}

export interface Move { player: string; from: number; to: number; walk: boolean }
export interface TradeSide { cash: number; squares: number[] }
export interface Trade { id: number; from: string; to: string; give: TradeSide; get: TradeSide }
export interface DrawnCard { deck: "chance" | "fund"; title: string; text: string; player: string; seq: number }

export interface BusinessView extends GameViewBase {
  board: Square[];
  rules: {
    start_cash: number; salary: number; jail_fine: number; income_tax: number;
    transport_rents: number[]; utility_multipliers: number[]; jail: number; go_to_jail: number; size: number;
  };
  players: BizPlayer[];
  owners: (string | null)[];
  houses: number[];
  mortgaged: boolean[];
  current: string | null;
  phase: Phase;
  dice: [number, number] | null;
  roll_seq: number;
  doubles: number;
  again: boolean;
  offer: { square: number; price: number; affordable: boolean } | null;
  debt: { debtor: string; creditor: string | null; amount: number; what: string; total: number; short: number } | null;
  trade: Trade | null;
  card: DrawnCard | null;
  moves: Move[];
  actions: string[];
  can_build: number[];
  can_sell: number[];
  can_mortgage: number[];
  can_unmortgage: number[];
  duration: number | null;
  ends_in_ms: number | null;
  result: { winners: string[]; draw: boolean; reason: string } | null;
}

export const SIZE = 36;
export const HOTEL = 5;

/** ₹ with Indian digit grouping (₹1,23,456). */
export const rupees = (n: number) => `${n < 0 ? "−" : ""}₹${Math.abs(n).toLocaleString("en-IN")}`;

/** Airport-style codes for tiny boards. */
export const CODES: Record<string, string> = {
  Agra: "AGR", Varanasi: "VNS", Jaipur: "JAI", Jodhpur: "JDH", Udaipur: "UDR", Bhopal: "BHO", Indore: "IDR",
  Nagpur: "NAG", Lucknow: "LKO", Kochi: "COK", Chandigarh: "IXC", Goa: "GOI", Pune: "PNQ", Ahmedabad: "AMD",
  Surat: "STV", Kolkata: "CCU", Hyderabad: "HYD", Chennai: "MAA", Bengaluru: "BLR", Gurugram: "GGN",
  Delhi: "DEL", Mumbai: "BOM",
};

export const ICONS: Partial<Record<string, string>> = {
  Railways: "🚆", Airways: "✈️", Waterways: "🚢", Roadways: "🚌",
  "Electricity Board": "💡", "Water Works": "🚰", "Income Tax": "🧾", "Community Fund": "🪙",
};

export type Side = "bottom" | "left" | "top" | "right" | "corner";

/** Grid cell (0–9) of a square: Start bottom-right, play runs clockwise (left along the bottom). */
export function cellOf(i: number): { row: number; col: number; side: Side } {
  if (i === 0) return { row: 9, col: 9, side: "corner" };
  if (i < 9) return { row: 9, col: 9 - i, side: "bottom" };
  if (i === 9) return { row: 9, col: 0, side: "corner" };
  if (i < 18) return { row: 18 - i, col: 0, side: "left" };
  if (i === 18) return { row: 0, col: 0, side: "corner" };
  if (i < 27) return { row: 0, col: i - 18, side: "top" };
  if (i === 27) return { row: 0, col: 9, side: "corner" };
  return { row: i - 27, col: 9, side: "right" };
}

/** Corners are 1.5 units, the other 8 cells 1 unit: 11 units across. */
const UNITS = 11;
function span(k: number): [number, number] {
  if (k === 0) return [0, 1.5];
  if (k === 9) return [9.5, 11];
  return [1.5 + (k - 1), 2.5 + (k - 1)];
}

/** Centre of a square's token area, in board % (0–100). */
export function tokenPoint(i: number): [number, number] {
  const { row, col, side } = cellOf(i);
  const [x0, x1] = span(col);
  const [y0, y1] = span(row);
  let x = (x0 + x1) / 2, y = (y0 + y1) / 2;
  // Keep tokens off the colour band, which sits on the inner edge.
  if (side === "bottom") y += 0.18;
  if (side === "top") y -= 0.18;
  if (side === "left") x -= 0.18;
  if (side === "right") x += 0.18;
  if (i === 9) { x = 0.34; y = 10.66; } // just visiting: the outer strip of the Jail corner
  return [(x / UNITS) * 100, (y / UNITS) * 100];
}

/** Where jailed (not visiting) tokens sit: the barred inner part of the Jail corner. */
export function jailPoint(): [number, number] {
  return [(1.02 / UNITS) * 100, (9.98 / UNITS) * 100];
}

/** Steps a token takes from `from` to `to`, following this view's recorded moves. */
export function hopPath(moves: Move[], player: string, from: number, to: number): number[] {
  const mine = moves.filter((m) => m.player === player);
  const steps: number[] = [];
  let cursor = from;
  for (const m of mine) {
    if (m.from !== cursor) continue;
    if (m.walk) {
      for (let s = (m.from + 1) % SIZE; ; s = (s + 1) % SIZE) {
        steps.push(s);
        if (s === m.to) break;
      }
    } else {
      steps.push(m.to);
    }
    cursor = m.to;
  }
  return cursor === to && steps.length ? steps : [to];
}

/** Squares of each colour group, in board order. */
export function groupsOf(board: Square[]): Map<string, Square[]> {
  const groups = new Map<string, Square[]>();
  for (const s of board) {
    if (!s.group) continue;
    groups.set(s.group, [...(groups.get(s.group) ?? []), s]);
  }
  return groups;
}

export const isProperty = (s: Square | undefined) => !!s && (s.kind === "city" || s.kind === "transport" || s.kind === "utility");

/** Properties a player can put into a trade: owned, and no buildings in the group. */
export function tradable(view: BusinessView, player: string): Square[] {
  return view.board.filter((s) => isProperty(s) && view.owners[s.index] === player && !(s.group &&
    view.board.some((o) => o.group === s.group && (view.houses[o.index] ?? 0) > 0)));
}
