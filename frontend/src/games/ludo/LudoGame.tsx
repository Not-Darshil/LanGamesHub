import { nameOf, type GameProps } from "..";
import type { GameViewBase } from "../../types";
import { GameLog } from "../GameLog";
import { HOME_COLUMN, TRACK, YARD_AREA, tokenCell, type Cell, type Color } from "./board";
import "./ludo.css";

interface LudoView extends GameViewBase {
  players: { id: string; color: Color }[];
  tokens: Record<string, number[]>;
  current: string | null;
  phase: "roll" | "move";
  roll: number | null;
  sixes: number;
  legal_tokens: number[];
  winner: string | null;
  start: Record<Color, number>;
  safe_squares: number[];
}

const DIE = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];
const key = ([r, c]: Cell) => `${r},${c}`;

export function LudoGame({ view, act }: GameProps<LudoView>) {
  const myTurn = view.current === view.you && !view.winner;
  const startCells = new Map(Object.entries(view.start).map(([c, s]) => [key(TRACK[s]!), c as Color]));
  const safe = new Set(view.safe_squares.map((s) => key(TRACK[s]!)));
  const homeCells = new Map<string, Color>();
  for (const [color, cells] of Object.entries(HOME_COLUMN)) {
    for (const cell of cells) homeCells.set(key(cell), color as Color);
  }
  const trackCells = new Set(TRACK.map(key));

  // Group tokens by cell so stacked tokens render side by side.
  const pieces = new Map<string, { player: string; index: number; color: Color; progress: number }[]>();
  for (const p of view.players) {
    (view.tokens[p.id] ?? []).forEach((progress, index) => {
      const cell = key(tokenCell(p.color, view.start[p.color], progress, index));
      const list = pieces.get(cell) ?? [];
      list.push({ player: p.id, index, color: p.color, progress });
      pieces.set(cell, list);
    });
  }

  const cells: React.ReactNode[] = [];
  for (let r = 0; r < 15; r++) {
    for (let c = 0; c < 15; c++) {
      const k = `${r},${c}`;
      const yard = (Object.entries(YARD_AREA) as [Color, { row: number; col: number }][])
        .find(([, a]) => r >= a.row && r < a.row + 6 && c >= a.col && c < a.col + 6)?.[0];
      const centerZone = r >= 6 && r <= 8 && c >= 6 && c <= 8;
      let cls = "lu-cell";
      if (yard) cls += ` lu-yard lu-${yard}-soft`;
      else if (centerZone) cls += " lu-center";
      else if (homeCells.has(k)) cls += ` lu-${homeCells.get(k)}`;
      else if (startCells.has(k)) cls += ` lu-${startCells.get(k)}`;
      else if (trackCells.has(k)) cls += " lu-track";
      else cls += " lu-blank";
      const here = pieces.get(k) ?? [];
      cells.push(
        <div key={k} className={cls} style={{ gridRow: r + 1, gridColumn: c + 1 }}>
          {safe.has(k) && !startCells.has(k) && <span className="lu-star">★</span>}
          {here.length > 0 && (
            <div className="lu-stack">
              {here.map((t) => {
                const movable = myTurn && t.player === view.you && view.legal_tokens.includes(t.index);
                return (
                  <button
                    key={`${t.player}-${t.index}`}
                    type="button"
                    className={`lu-token lu-${t.color} ${movable ? "lu-movable" : ""}`}
                    disabled={!movable}
                    title={`${nameOf(view, t.player)} token ${t.index + 1}`}
                    onClick={() => void act({ type: "move", token: t.index }).catch(() => {})}
                  >
                    {t.progress === 56 ? "✓" : t.index + 1}
                  </button>
                );
              })}
            </div>
          )}
        </div>,
      );
    }
  }

  const homeCount = (id: string) => (view.tokens[id] ?? []).filter((t) => t === 56).length;

  return (
    <div className="game ludo game-columns">
      <div className="lu-board" aria-label="Ludo board">
        {cells}
      </div>
      <div className="lu-side">
        <ul className="plain lu-legend">
          {view.players.map((p) => (
            <li key={p.id} className={p.id === view.current ? "lu-turn" : ""}>
              <span className={`lu-dot lu-${p.color}`} />
              {nameOf(view, p.id)} ({p.color}) — {homeCount(p.id)}/4 home
            </li>
          ))}
        </ul>
        <p className="game-status">
          {view.winner ? `${nameOf(view, view.winner)} won!` : myTurn
            ? view.phase === "roll" ? "Your turn — roll the die" : "Choose a token to move"
            : `${nameOf(view, view.current)}'s turn`}
        </p>
        {view.roll !== null && (
          <p className="lu-roll"><span className="lu-die">{DIE[view.roll]}</span> {nameOf(view, view.current)} rolled {view.roll}
            {view.sixes > 0 && view.phase === "roll" && !view.winner ? " — roll again!" : ""}</p>
        )}
        <button disabled={!myTurn || view.phase !== "roll"} onClick={() => void act({ type: "roll" }).catch(() => {})}>
          Roll the die
        </button>
        <p className="muted small-print">A 6 brings a token out and earns another roll. Exact roll to reach home. ★ squares and start squares are safe.</p>
        <GameLog view={view} />
      </div>
    </div>
  );
}
