import { nameOf, type GameProps } from "..";
import type { GameViewBase } from "../../types";
import { seatColor } from "../colors";
import { GameLog } from "../GameLog";
import "./snakes.css";

interface SnakesView extends GameViewBase {
  players: string[];
  positions: Record<string, number>;
  current: string | null;
  last_roll: { player: string; roll: number; from: number; landed: number; to: number;
    jump: "ladder" | "snake" | null } | null;
  winner: string | null;
  ladders: Record<string, number>;
  snakes: Record<string, number>;
}

const DIE = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];

/** Board coordinates (0–9, origin bottom-left) for square 1–100, boustrophedon. */
function cell(square: number): { row: number; col: number } {
  const row = Math.floor((square - 1) / 10);
  const offset = (square - 1) % 10;
  return { row, col: row % 2 === 0 ? offset : 9 - offset };
}

function center(square: number): [number, number] {
  const { row, col } = cell(square);
  return [col * 10 + 5, (9 - row) * 10 + 5];
}

export function SnakesGame({ view, act }: GameProps<SnakesView>) {
  const myTurn = view.current === view.you && !view.winner;
  const squares = Array.from({ length: 100 }, (_, i) => i + 1);
  const offBoard = view.players.filter((p) => (view.positions[p] ?? 0) === 0);
  const last = view.last_roll;

  return (
    <div className="game snakes game-columns">
      <div className="sl-board-wrap">
        <div className="sl-board">
          {squares.map((n) => {
            const { row, col } = cell(n);
            const here = view.players.filter((p) => view.positions[p] === n);
            return (
              <div key={n} className={`sl-cell ${(row + col) % 2 ? "sl-dark" : ""}`}
                style={{ gridRow: 10 - row, gridColumn: col + 1 }}>
                <span className="sl-num">{n}</span>
                <div className="sl-tokens">
                  {here.map((p) => (
                    <span key={p} className="sl-token" title={nameOf(view, p)}
                      style={{ background: seatColor(view, p) }} />
                  ))}
                </div>
              </div>
            );
          })}
          <svg className="sl-overlay" viewBox="0 0 100 100" aria-hidden="true">
            {Object.entries(view.ladders).map(([from, to]) => {
              const [x1, y1] = center(Number(from));
              const [x2, y2] = center(to);
              return <line key={`l${from}`} x1={x1} y1={y1} x2={x2} y2={y2} className="sl-ladder" />;
            })}
            {Object.entries(view.snakes).map(([from, to]) => {
              const [x1, y1] = center(Number(from));
              const [x2, y2] = center(to);
              const mx = (x1 + x2) / 2 + (y2 - y1) * 0.2;
              const my = (y1 + y2) / 2 + (x1 - x2) * 0.2;
              return (
                <g key={`s${from}`}>
                  <path d={`M${x1},${y1} Q${mx},${my} ${x2},${y2}`} className="sl-snake" />
                  <circle cx={x1} cy={y1} r={1.8} className="sl-snake-head" />
                </g>
              );
            })}
          </svg>
        </div>
        {offBoard.length > 0 && (
          <p className="muted">Not on the board yet: {offBoard.map((p) => nameOf(view, p)).join(", ")}</p>
        )}
      </div>

      <div className="sl-side">
        <ul className="plain sl-legend">
          {view.players.map((p) => (
            <li key={p} className={p === view.current ? "sl-turn" : ""}>
              <span className="sl-token" style={{ background: seatColor(view, p) }} />
              {nameOf(view, p)} — square {view.positions[p] ?? 0}
            </li>
          ))}
        </ul>
        <p className="game-status">
          {view.winner ? `${nameOf(view, view.winner)} won!` : myTurn ? "Your turn" : `${nameOf(view, view.current)}'s turn`}
        </p>
        {last && (
          <p className="sl-last">
            <span className="sl-die">{DIE[last.roll]}</span>
            {nameOf(view, last.player)} rolled {last.roll}
            {last.from === last.to && last.landed !== last.to && last.jump === null ? " (needs an exact roll)" : ""}
            {last.jump === "ladder" && ` — ladder to ${last.to}!`}
            {last.jump === "snake" && ` — snake down to ${last.to}`}
          </p>
        )}
        <button disabled={!myTurn} onClick={() => void act({ type: "roll" }).catch(() => {})}>
          Roll the die
        </button>
        <p className="muted small-print">Land exactly on 100 to win.</p>
        <GameLog view={view} />
      </div>
    </div>
  );
}
