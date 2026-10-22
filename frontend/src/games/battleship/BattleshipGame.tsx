import { useMemo, useState } from "react";
import { nameOf, type GameProps } from "..";
import type { GameViewBase } from "../../types";
import { GameLog } from "../GameLog";
import "./battleship.css";

type Orientation = "H" | "V";
interface Ship { ship: string; cells: [number, number][] }
interface Shot { row: number; col: number; result: "miss" | "hit" | "sunk"; ship?: string }

interface BattleshipView extends GameViewBase {
  phase: "placement" | "battle";
  players: string[];
  current: string | null;
  placed: Record<string, boolean>;
  winner: string | null;
  size: number;
  fleet_spec: Record<string, number>;
  my_fleet: Ship[] | null;
  incoming: Shot[];
  my_shots: Shot[];
  enemy_sunk: string[];
  my_sunk: string[];
}

const ROWS = "ABCDEFGHIJ";
const NAMES: Record<string, string> = {
  carrier: "Carrier", battleship: "Battleship", cruiser: "Cruiser", submarine: "Submarine", destroyer: "Destroyer",
};
const key = (r: number, c: number) => `${r},${c}`;

function cellsFor(r: number, c: number, o: Orientation, length: number): [number, number][] {
  return Array.from({ length }, (_, i) => (o === "H" ? [r, c + i] : [r + i, c]) as [number, number]);
}

function Grid({ size, render, onCell, onHover, label }: {
  size: number; label: string;
  render: (r: number, c: number) => { cls: string; mark?: string };
  onCell?: (r: number, c: number) => void;
  onHover?: (r: number, c: number) => void;
}) {
  return (
    <div className="bs-grid-wrap">
      <h3>{label}</h3>
      <div className="bs-grid" style={{ gridTemplateColumns: `24px repeat(${size}, 1fr)` }}>
        <span />
        {Array.from({ length: size }, (_, c) => <span key={`h${c}`} className="bs-label">{c + 1}</span>)}
        {Array.from({ length: size }, (_, r) => [
          <span key={`r${r}`} className="bs-label">{ROWS[r]}</span>,
          ...Array.from({ length: size }, (_, c) => {
            const { cls, mark } = render(r, c);
            return (
              <button key={key(r, c)} type="button" className={`bs-cell ${cls}`}
                disabled={!onCell} onClick={onCell ? () => onCell(r, c) : undefined}
                onMouseEnter={onHover ? () => onHover(r, c) : undefined}
                aria-label={`${ROWS[r]}${c + 1}`}>
                {mark}
              </button>
            );
          }),
        ])}
      </div>
    </div>
  );
}

function Placement({ view, act }: GameProps<BattleshipView>) {
  const spec = Object.entries(view.fleet_spec);
  const [orientation, setOrientation] = useState<Orientation>("H");
  const [placed, setPlaced] = useState<Record<string, { row: number; col: number; orientation: Orientation }>>({});
  const [selected, setSelected] = useState<string | null>(spec[0]?.[0] ?? null);
  const [hover, setHover] = useState<[number, number] | null>(null);

  const occupied = useMemo(() => {
    const map = new Map<string, string>();
    for (const [ship, p] of Object.entries(placed)) {
      for (const [r, c] of cellsFor(p.row, p.col, p.orientation, view.fleet_spec[ship] ?? 0)) map.set(key(r, c), ship);
    }
    return map;
  }, [placed, view.fleet_spec]);

  const preview = selected && hover ? cellsFor(hover[0], hover[1], orientation, view.fleet_spec[selected] ?? 0) : [];
  const previewOk = preview.every(([r, c]) => r < view.size && c < view.size && !occupied.has(key(r, c)));
  const previewKeys = new Set(preview.map(([r, c]) => key(r, c)));

  const onCell = (r: number, c: number) => {
    const existing = occupied.get(key(r, c));
    if (existing) {
      const next = { ...placed };
      delete next[existing];
      setPlaced(next);
      setSelected(existing);
      return;
    }
    if (!selected) return;
    const cells = cellsFor(r, c, orientation, view.fleet_spec[selected] ?? 0);
    if (!cells.every(([cr, cc]) => cr < view.size && cc < view.size && !occupied.has(key(cr, cc)))) return;
    const next = { ...placed, [selected]: { row: r, col: c, orientation } };
    setPlaced(next);
    setSelected(spec.find(([s]) => !next[s])?.[0] ?? null);
  };

  const complete = spec.every(([s]) => placed[s]);
  return (
    <div className="game-columns">
      <div onMouseLeave={() => setHover(null)}>
        <Grid size={view.size} label="Place your fleet" onCell={onCell}
          onHover={(r, c) => setHover([r, c])}
          render={(r, c) => {
            const k = key(r, c);
            if (occupied.has(k)) return { cls: "bs-ship" };
            if (previewKeys.has(k)) return { cls: previewOk ? "bs-preview" : "bs-preview-bad" };
            return { cls: "" };
          }} />
      </div>
      <div className="bs-side">
        <p>Select a ship, then click the board to place its bow. Click a placed ship to pick it up.</p>
        <ul className="plain bs-ships">
          {spec.map(([ship, length]) => (
            <li key={ship}>
              <button className={selected === ship ? "" : "secondary"} onClick={() => setSelected(ship)}
                disabled={Boolean(placed[ship])}>
                {NAMES[ship]} ({length}) {placed[ship] ? "✓" : ""}
              </button>
            </li>
          ))}
        </ul>
        <div className="row wrap">
          <button className="secondary" onClick={() => setOrientation(orientation === "H" ? "V" : "H")}>
            Rotate ({orientation === "H" ? "horizontal" : "vertical"})
          </button>
          <button className="secondary" onClick={() => setPlaced({})}>Clear</button>
        </div>
        <div className="row wrap bs-confirm">
          <button disabled={!complete} onClick={() => void act({
            type: "place",
            ships: Object.entries(placed).map(([ship, p]) => ({ ship, ...p })),
          }).catch(() => {})}>
            Confirm fleet
          </button>
          <button className="secondary" onClick={() => void act({ type: "place_random" }).catch(() => {})}>
            Place randomly
          </button>
        </div>
        <p className="muted small-print">Placement is final once confirmed. Your opponent never sees it.</p>
      </div>
    </div>
  );
}

export function BattleshipGame(props: GameProps<BattleshipView>) {
  const { view, act } = props;
  const opponent = view.players.find((p) => p !== view.you) ?? null;

  if (view.phase === "placement") {
    if (!view.placed[view.you]) {
      return <div className="game battleship bs-placement"><Placement {...props} /><GameLog view={view} /></div>;
    }
    return (
      <div className="game battleship">
        <p className="game-status">Fleet placed. Waiting for {nameOf(view, opponent)} to place theirs…</p>
        <GameLog view={view} />
      </div>
    );
  }

  const myTurn = view.current === view.you && !view.winner;
  const shipAt = new Map<string, string>();
  for (const ship of view.my_fleet ?? []) for (const [r, c] of ship.cells) shipAt.set(key(r, c), ship.ship);
  const incoming = new Map(view.incoming.map((s) => [key(s.row, s.col), s]));
  const shots = new Map(view.my_shots.map((s) => [key(s.row, s.col), s]));

  return (
    <div className="game battleship">
      <p className="game-status">
        {view.winner ? `${nameOf(view, view.winner)} won!` : myTurn ? "Your turn — fire at the enemy waters" : `${nameOf(view, opponent)} is aiming…`}
      </p>
      <div className="game-columns">
        <Grid size={view.size} label="Enemy waters"
          onCell={myTurn ? (r, c) => { if (!shots.has(key(r, c))) void act({ type: "fire", row: r, col: c }).catch(() => {}); } : undefined}
          render={(r, c) => {
            const shot = shots.get(key(r, c));
            if (!shot) return { cls: myTurn ? "bs-target" : "" };
            return shot.result === "miss" ? { cls: "bs-miss", mark: "•" } : { cls: shot.result === "sunk" ? "bs-sunk" : "bs-hit", mark: "✕" };
          }} />
        <Grid size={view.size} label="Your fleet"
          render={(r, c) => {
            const k = key(r, c);
            const hit = incoming.get(k);
            const cls = shipAt.has(k) ? "bs-ship" : "";
            if (!hit) return { cls };
            if (hit.result === "miss") return { cls: `${cls} bs-miss`, mark: "•" };
            const sunk = view.my_sunk.includes(shipAt.get(k) ?? "");
            return { cls: sunk ? "bs-ship bs-sunk" : "bs-ship bs-hit", mark: "✕" };
          }} />
      </div>
      <p className="muted">
        Enemy ships sunk: {view.enemy_sunk.map((s) => NAMES[s]).join(", ") || "none"} · Your ships lost:{" "}
        {view.my_sunk.map((s) => NAMES[s]).join(", ") || "none"}
      </p>
      <GameLog view={view} />
    </div>
  );
}
