import {
  useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent, type ReactNode,
} from "react";
import { nameOf, type GameProps } from "..";
import type { GameViewBase } from "../../types";
import { Avatar } from "../../ui/Avatar";
import { useTurnAlert } from "../../ui/hooks";
import { Icon } from "../../ui/Icon";
import { play } from "../../ui/sound";
import { GameLog } from "../GameLog";
import "./battleship.css";

type Orientation = "H" | "V";
type Cell = [number, number];
type Result = "miss" | "hit" | "sunk";
interface Ship { ship: string; cells: Cell[] }
interface Shot { row: number; col: number; result: Result; ship?: string }

interface BattleshipView extends GameViewBase {
  phase: "placement" | "battle";
  players: string[];
  current: string | null;
  placed: Record<string, boolean>;
  winner: string | null;
  size: number;
  fleet_spec: Record<string, number>;
  // Absent for spectators.
  my_fleet?: Ship[] | null;
  incoming?: Shot[];
  my_shots?: Shot[];
  enemy_sunk?: string[];
  my_sunk?: string[];
}

const ROWS = "ABCDEFGHIJ";
const NAMES: Record<string, string> = {
  carrier: "Carrier", battleship: "Battleship", cruiser: "Cruiser", submarine: "Submarine", destroyer: "Destroyer",
};
const NO_SHOTS: Shot[] = [];
const key = (r: number, c: number) => `${r},${c}`;
const coord = (r: number, c: number) => `${ROWS[r] ?? "?"}${c + 1}`;
const shipName = (ship: string | undefined) => (ship ? NAMES[ship] ?? ship : "ship");

/** One hull segment: index along the ship, ship length and orientation (for bow/stern shapes). */
interface Seg { i: number; n: number; o: Orientation; ship: string }

function cellsFor(r: number, c: number, o: Orientation, length: number): Cell[] {
  return Array.from({ length }, (_, i) => (o === "H" ? [r, c + i] : [r + i, c]) as Cell);
}

function addSegments(cells: Cell[], ship: string, into: Map<string, Seg>, o?: Orientation): void {
  const sorted = o ? cells : [...cells].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const dir = o ?? (sorted.length > 1 && sorted[0]![0] === sorted[1]![0] ? "H" : "V");
  sorted.forEach(([r, c], i) => into.set(key(r, c), { i, n: sorted.length, o: dir, ship }));
}

/** The enemy layout is secret, but a sunk ship must be a straight run of our hits through the sinking shot. */
function inferSunk(shots: Shot[], spec: Record<string, number>): Map<string, Seg> {
  const hits = new Set(shots.filter((s) => s.result !== "miss").map((s) => key(s.row, s.col)));
  const out = new Map<string, Seg>();
  for (const s of shots) {
    if (s.result !== "sunk" || !s.ship) continue;
    const n = spec[s.ship] ?? 0;
    for (const o of ["H", "V"] as const) {
      const line = Array.from({ length: n }, (_, off) =>
        o === "H" ? cellsFor(s.row, s.col - off, o, n) : cellsFor(s.row - off, s.col, o, n))
        .find((cells) => cells.every(([r, c]) => hits.has(key(r, c)) && !out.has(key(r, c))));
      if (line) { addSegments(line, s.ship, out, o); break; }
    }
  }
  return out;
}

/** Shot keys that just arrived ("e" = my shots, "f" = incoming), for one-shot animations + sounds. */
function useFreshShots(mine: Shot[], incoming: Shot[]): ReadonlySet<string> {
  const seen = useRef<Set<string> | null>(null);
  const timers = useRef<number[]>([]);
  const [fresh, setFresh] = useState<ReadonlySet<string>>(() => new Set());
  useLayoutEffect(() => {
    const all = [
      ...mine.map((s) => [`e${key(s.row, s.col)}`, s] as const),
      ...incoming.map((s) => [`f${key(s.row, s.col)}`, s] as const),
    ];
    const known = seen.current;
    if (!known) { seen.current = new Set(all.map(([k]) => k)); return; }
    const added = all.filter(([k]) => !known.has(k));
    if (added.length === 0) return;
    const keys = added.map(([k]) => k);
    keys.forEach((k) => known.add(k));
    play(added.some(([, s]) => s.result !== "miss") ? "boom" : "splash");
    setFresh((prev) => new Set([...prev, ...keys]));
    timers.current.push(window.setTimeout(() => setFresh((prev) => {
      const next = new Set(prev);
      keys.forEach((k) => next.delete(k));
      return next;
    }), 1600));
  }, [mine, incoming]);
  useEffect(() => {
    const list = timers.current;
    return () => list.forEach((t) => window.clearTimeout(t));
  }, []);
  return fresh;
}

interface Look { cls?: string; seg?: Seg; mark?: Result; fresh?: boolean; delay?: number; off?: boolean }
interface Callout { id: string; text: string; tone: Result }

function Board({ label, size, look, onCell, onHover, onLeave, onContext, className = "", aside, callout }: {
  label: string; size: number; look: (r: number, c: number) => Look;
  onCell?: (r: number, c: number) => void; onHover?: (r: number, c: number) => void;
  onLeave?: () => void; onContext?: (e: MouseEvent) => void;
  className?: string; aside?: ReactNode; callout?: Callout | null;
}) {
  const range = Array.from({ length: size }, (_, i) => i);
  return (
    <section className={`bs-grid-wrap ${className}`}>
      <header className="bs-board-head"><h3>{label}</h3>{aside}</header>
      <div className="bs-board" onMouseLeave={onLeave} onContextMenu={onContext}>
        <div className="bs-cols" aria-hidden="true">{range.map((c) => <span key={c}>{c + 1}</span>)}</div>
        <div className="bs-rows" aria-hidden="true">{range.map((r) => <span key={r}>{ROWS[r]}</span>)}</div>
        <div className="bs-sea" style={{ ["--n" as string]: size } as CSSProperties}>
          {range.map((r) => range.map((c) => {
            const l = look(r, c);
            const { seg } = l;
            return (
              <button key={key(r, c)} type="button" className={`bs-cell ${l.cls ?? ""}`} aria-label={coord(r, c)}
                disabled={!onCell || l.off} onClick={onCell && (() => onCell(r, c))}
                onMouseEnter={onHover && (() => onHover(r, c))}
                style={l.delay ? ({ ["--d" as string]: `${l.delay}ms` } as CSSProperties) : undefined}>
                {seg && <span className={`bs-hull ${seg.o === "H" ? "h" : "v"}${seg.i === 0 ? " bow" : ""}${
                  seg.i === seg.n - 1 ? " stern" : ""}${seg.i > 0 && seg.i < seg.n - 1 && seg.i % 2 ? " turret" : ""}`} />}
                {l.mark && <span className={`bs-mark ${l.mark}${l.fresh ? " fresh" : ""}`} />}
              </button>
            );
          }))}
          {callout && <div key={callout.id} className={`bs-callout ${callout.tone}`}>{callout.text}</div>}
        </div>
      </div>
    </section>
  );
}

function Pips({ n, hit = () => false, sunk }: { n: number; hit?: (i: number) => boolean; sunk?: boolean }) {
  return (
    <span className={`bs-pips${sunk ? " sunk" : ""}`} aria-hidden="true">
      {Array.from({ length: n }, (_, i) => <i key={i} className={hit(i) ? "hit" : ""} />)}
    </span>
  );
}

interface Placed { row: number; col: number; orientation: Orientation }

function Placement({ view, act }: GameProps<BattleshipView>) {
  const spec = Object.entries(view.fleet_spec);
  const [orientation, setOrientation] = useState<Orientation>("H");
  const [placed, setPlaced] = useState<Record<string, Placed>>({});
  const [selected, setSelected] = useState<string | null>(spec[0]?.[0] ?? null);
  const [hover, setHover] = useState<Cell | null>(null);
  const [lastPlaced, setLastPlaced] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const rotate = () => setOrientation((o) => (o === "H" ? "V" : "H"));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key !== "r" && e.key !== "R") || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      setOrientation((o) => (o === "H" ? "V" : "H"));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const occupied = useMemo(() => {
    const map = new Map<string, Seg>();
    for (const [ship, p] of Object.entries(placed)) {
      addSegments(cellsFor(p.row, p.col, p.orientation, view.fleet_spec[ship] ?? 0), ship, map, p.orientation);
    }
    return map;
  }, [placed, view.fleet_spec]);

  const fits = (cells: Cell[]) =>
    cells.every(([r, c]) => r < view.size && c < view.size && !occupied.has(key(r, c)));
  const preview = new Map<string, Seg>();
  const previewCells = selected && hover ? cellsFor(hover[0], hover[1], orientation, view.fleet_spec[selected] ?? 0) : [];
  if (selected) addSegments(previewCells, selected, preview, orientation);
  const previewOk = fits(previewCells);

  const onCell = (r: number, c: number) => {
    const existing = occupied.get(key(r, c));
    if (existing) {
      const next = { ...placed };
      const was = next[existing.ship];
      delete next[existing.ship];
      setPlaced(next);
      setSelected(existing.ship);
      if (was) setOrientation(was.orientation);
      play("pop");
      return;
    }
    if (!selected) return;
    if (!fits(cellsFor(r, c, orientation, view.fleet_spec[selected] ?? 0))) { play("error"); return; }
    const next = { ...placed, [selected]: { row: r, col: c, orientation } };
    setPlaced(next);
    setLastPlaced(selected);
    setSelected(spec.find(([s]) => !next[s])?.[0] ?? null);
    play("pop");
  };

  const send = (action: Record<string, unknown>) => {
    setBusy(true);
    void act(action).catch(() => setBusy(false));
  };
  const count = Object.keys(placed).length;
  const complete = spec.every(([s]) => placed[s]);
  const hint = selected
    ? `Click a square to deploy your ${shipName(selected)} (${view.fleet_spec[selected]} cells).`
    : complete ? "Fleet ready. Confirm to set sail." : "Pick a ship to deploy.";

  return (
    <div className="game-layout">
      <div className="bs-main">
        <p className="game-status mine">
          <Icon name="target" size={18} /> Deploy your fleet · {count}/{spec.length} placed
        </p>
        <Board size={view.size} label="Place your fleet" className={`bs-placing${selected ? " has-sel" : ""}`}
          onCell={onCell} onHover={(r, c) => setHover([r, c])} onLeave={() => setHover(null)}
          onContext={(e) => { e.preventDefault(); rotate(); }}
          aside={<span className="pill">{orientation === "H" ? "Horizontal" : "Vertical"} <span className="kbd">R</span></span>}
          look={(r, c) => {
            const k = key(r, c);
            const occ = occupied.get(k);
            if (occ) return { cls: `bs-ship${occ.ship === lastPlaced ? " bs-drop" : ""}`, seg: occ, delay: occ.i * 45 };
            const pv = preview.get(k);
            if (pv) return { cls: previewOk ? "bs-preview" : "bs-preview-bad", seg: pv };
            return {};
          }} />
      </div>
      <aside className="side-panel bs-dock">
        <h3>Shipyard</h3>
        <p className="bs-hint">{hint}</p>
        <ul className="bs-picker">
          {spec.map(([ship, length]) => {
            const isPlaced = Boolean(placed[ship]);
            return (
              <li key={ship}>
                <button type="button" className={`bs-pick${selected === ship ? " is-sel" : ""}${isPlaced ? " is-placed" : ""}`}
                  onClick={() => {
                    if (isPlaced) { const next = { ...placed }; delete next[ship]; setPlaced(next); }
                    setSelected(ship);
                  }}>
                  <span className="bs-pick-name"><strong>{shipName(ship)}</strong><small>{length} cells</small></span>
                  <Pips n={length} />
                  <span className="bs-pick-state">{isPlaced ? <Icon name="check" size={16} /> : null}</span>
                </button>
              </li>
            );
          })}
        </ul>
        <div className="bs-tools">
          <button type="button" className="secondary" onClick={rotate}>
            <Icon name="rotate" size={16} /> Rotate <span className="kbd">R</span>
          </button>
          <button type="button" className="secondary" disabled={count === 0}
            onClick={() => { setPlaced({}); setSelected(spec[0]?.[0] ?? null); }}>
            <Icon name="x" size={16} /> Clear
          </button>
        </div>
        <button type="button" className="large block" disabled={!complete || busy}
          onClick={() => send({ type: "place", ships: Object.entries(placed).map(([ship, p]) => ({ ship, ...p })) })}>
          <Icon name="check" size={18} /> Confirm fleet
        </button>
        <button type="button" className="secondary block" disabled={busy} onClick={() => send({ type: "place_random" })}>
          <Icon name="shuffle" size={16} /> Place randomly
        </button>
        <p className="muted small-print">Right-click the board to rotate too. Placement is final once confirmed; your opponent never sees it.</p>
      </aside>
    </div>
  );
}

function PlayerRows({ view, sub }: { view: BattleshipView; sub: (p: string) => string }) {
  return (
    <ul className="player-list">
      {view.players.map((p) => (
        <li key={p} className={`player-row${view.current === p && !view.winner ? " is-turn" : ""}`}>
          <Avatar name={view.names[p] ?? "Player"} size={30} />
          <div className="grow"><div>{nameOf(view, p)}</div><div className="sub">{sub(p)}</div></div>
          {view.current === p && !view.winner && <span className="turn-chip">Firing</span>}
          {view.winner === p && <Icon name="crown" size={16} className="bs-crown" />}
        </li>
      ))}
    </ul>
  );
}

function Waiting({ view, opponent }: { view: BattleshipView; opponent: string | null }) {
  const fleet = useMemo(() => {
    const m = new Map<string, Seg>();
    for (const s of view.my_fleet ?? []) addSegments(s.cells, s.ship, m);
    return m;
  }, [view.my_fleet]);
  return (
    <div className="game-layout">
      <div className="bs-main">
        <div className="bs-radar-card">
          <div className="bs-radar" aria-hidden="true"><span className="sweep" /><i /><i /><i /></div>
          <div>
            <p className="bs-wait-title">Fleet placed. Waiting for {nameOf(view, opponent) || "your opponent"} to place theirs…</p>
            <p className="muted small-print">Your ships are hidden from the enemy. Battle starts once both fleets are deployed.</p>
          </div>
        </div>
        <Board size={view.size} label="Your fleet" className="bs-readonly"
          look={(r, c) => { const seg = fleet.get(key(r, c)); return seg ? { cls: "bs-ship", seg } : {}; }} />
      </div>
      <aside className="side-panel">
        <h3>Players</h3>
        <PlayerRows view={view} sub={(p) => (view.placed[p] ? "Fleet deployed" : "Deploying…")} />
        <GameLog view={view} />
      </aside>
    </div>
  );
}

function Battle({ view, act, opponent }: GameProps<BattleshipView> & { opponent: string | null }) {
  const myTurn = view.current === view.you && !view.winner;
  useTurnAlert(myTurn);
  const myShots = view.my_shots ?? NO_SHOTS;
  const incoming = view.incoming ?? NO_SHOTS;
  const fresh = useFreshShots(myShots, incoming);
  const [pending, setPending] = useState<string | null>(null);
  const [aim, setAim] = useState<Cell | null>(null);
  useEffect(() => setPending(null), [myShots.length, view.current]);

  const fleetSeg = useMemo(() => {
    const m = new Map<string, Seg>();
    for (const s of view.my_fleet ?? []) addSegments(s.cells, s.ship, m);
    return m;
  }, [view.my_fleet]);
  const enemySeg = useMemo(() => inferSunk(myShots, view.fleet_spec), [myShots, view.fleet_spec]);
  const shotAt = new Map(myShots.map((s) => [key(s.row, s.col), s]));
  const hitAt = new Map(incoming.map((s) => [key(s.row, s.col), s]));
  const mySunk = new Set(view.my_sunk ?? []);
  const enemySunk = new Set(view.enemy_sunk ?? []);
  const sinking = (shots: Shot[], prefix: string) =>
    new Set(shots.filter((s) => s.result === "sunk" && fresh.has(prefix + key(s.row, s.col))).map((s) => s.ship));
  const enemySinking = sinking(myShots, "e");
  const mySinking = sinking(incoming, "f");

  const callout = (shot: Shot | undefined, prefix: string, sunkText: (s: string) => string): Callout | null => {
    if (!shot || !fresh.has(prefix + key(shot.row, shot.col))) return null;
    const text = shot.result === "miss" ? "Miss" : shot.result === "hit" ? "Hit!" : sunkText(shipName(shot.ship));
    return { id: prefix + key(shot.row, shot.col), text, tone: shot.result };
  };
  const enemyCallout = callout(myShots[myShots.length - 1], "e", (s) => `${s} sunk!`);
  const fleetCallout = callout(incoming[incoming.length - 1], "f", (s) => `${s} lost!`);

  const fire = (r: number, c: number) => {
    const k = key(r, c);
    if (!myTurn || pending || shotAt.has(k)) return;
    setPending(k);
    void act({ type: "fire", row: r, col: c }).catch(() => setPending(null));
  };

  const hits = myShots.filter((s) => s.result !== "miss").length;
  const accuracy = myShots.length ? `${Math.round((hits / myShots.length) * 100)}%` : "—";
  const spec = Object.entries(view.fleet_spec);
  const afloat = spec.length - mySunk.size;
  const status = view.winner
    ? view.winner === view.you ? "Victory! You won the battle" : `${nameOf(view, view.winner)} won the battle`
    : myTurn ? "Your turn — fire at the enemy waters" : `${nameOf(view, opponent) || "Opponent"} is aiming…`;

  return (
    <div className="game-layout">
      <div className="bs-main">
        <p className={`game-status${myTurn ? " mine" : ""}${view.winner ? " over" : ""}`}>
          <Icon name={view.winner ? "trophy" : myTurn ? "target" : "clock"} size={18} />
          {status}
        </p>
        <div className="bs-boards">
          <Board size={view.size} label="Enemy waters" callout={enemyCallout}
            className={myTurn ? "bs-enemy is-live" : view.winner ? "bs-enemy" : "bs-enemy is-dim"}
            onCell={myTurn ? fire : undefined} onHover={myTurn ? (r, c) => setAim([r, c]) : undefined}
            onLeave={() => setAim(null)}
            aside={myTurn
              ? <span className="pill accent bs-aim">{aim ? `Aim ${coord(aim[0], aim[1])}` : "Fire at will"}</span>
              : <span className="pill">{enemySunk.size}/{spec.length} sunk</span>}
            look={(r, c) => {
              const k = key(r, c);
              const shot = shotAt.get(k);
              if (!shot) return { cls: myTurn ? `bs-target${pending === k ? " bs-locking" : ""}` : "" };
              const isFresh = fresh.has(`e${k}`);
              const seg = enemySeg.get(k);
              if (seg) {
                return { cls: `bs-hit bs-sunk${enemySinking.has(seg.ship) ? " bs-sinking" : ""}`, seg, mark: "sunk",
                  fresh: isFresh, delay: seg.i * 90, off: true };
              }
              return { cls: shot.result === "miss" ? "bs-miss" : "bs-hit", mark: shot.result === "miss" ? "miss" : "hit",
                fresh: isFresh, off: true };
            }} />
          <Board size={view.size} label="Your fleet" callout={fleetCallout}
            className={`bs-own${fleetCallout && fleetCallout.tone !== "miss" ? " bs-quake" : ""}`}
            aside={<span className={`pill${afloat <= 1 ? " danger" : ""}`}>{afloat}/{spec.length} afloat</span>}
            look={(r, c) => {
              const k = key(r, c);
              const seg = fleetSeg.get(k);
              const hit = hitAt.get(k);
              const base = seg ? "bs-ship" : "";
              if (!hit) return { cls: base, seg };
              const isFresh = fresh.has(`f${k}`);
              if (hit.result === "miss") return { cls: `${base} bs-miss`, seg, mark: "miss", fresh: isFresh };
              const sunk = Boolean(seg && mySunk.has(seg.ship));
              const cls = sunk ? `bs-hit bs-sunk${seg && mySinking.has(seg.ship) ? " bs-sinking" : ""}` : "bs-hit";
              return { cls: `bs-ship ${cls}`, seg, mark: sunk ? "sunk" : "hit", fresh: isFresh, delay: (seg?.i ?? 0) * 90 };
            }} />
        </div>
      </div>
      <aside className="side-panel">
        <h3>Players</h3>
        <PlayerRows view={view} sub={(p) => {
          const lost = p === view.you ? mySunk.size : enemySunk.size;
          return `${spec.length - lost}/${spec.length} ships afloat`;
        }} />
        <div className="bs-stats">
          <div><strong>{myShots.length}</strong><span>Shots</span></div>
          <div><strong>{hits}</strong><span>Hits</span></div>
          <div><strong>{accuracy}</strong><span>Accuracy</span></div>
        </div>
        <h3>Enemy fleet</h3>
        <ul className="bs-fleet">
          {spec.map(([ship, n]) => (
            <li key={ship} className={enemySunk.has(ship) ? "sunk" : ""}>
              <span>{shipName(ship)}</span><Pips n={n} hit={() => enemySunk.has(ship)} sunk={enemySunk.has(ship)} />
            </li>
          ))}
        </ul>
        <h3>Your ships</h3>
        <ul className="bs-fleet">
          {spec.map(([ship, n]) => {
            const damaged = new Set([...fleetSeg].filter(([k, s]) => s.ship === ship && hitAt.has(k)).map(([, s]) => s.i));
            return (
              <li key={ship} className={mySunk.has(ship) ? "sunk" : ""}>
                <span>{shipName(ship)}</span><Pips n={n} sunk={mySunk.has(ship)} hit={(i) => damaged.has(i)} />
              </li>
            );
          })}
        </ul>
        <GameLog view={view} />
      </aside>
    </div>
  );
}

export function BattleshipGame(props: GameProps<BattleshipView>) {
  const { view } = props;
  const opponent = view.players.find((p) => p !== view.you) ?? null;
  let body: ReactNode;
  let phase: string;
  if (view.phase === "battle") {
    phase = "bs-battle";
    body = <Battle {...props} opponent={opponent} />;
  } else if (view.placed[view.you]) {
    phase = "bs-waiting";
    body = <Waiting view={view} opponent={opponent} />;
  } else {
    phase = "bs-placement";
    body = <Placement {...props} />;
  }
  return <div className={`game battleship ${phase}`}>{body}</div>;
}
