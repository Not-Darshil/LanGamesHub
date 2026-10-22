import { useEffect, useRef, useState, type CSSProperties } from "react";
import { nameOf, type GameProps } from "..";
import type { GameViewBase } from "../../types";
import { Avatar } from "../../ui/Avatar";
import { Die } from "../../ui/Dice";
import { Icon } from "../../ui/Icon";
import { useFlash, useStepped, useTurnAlert } from "../../ui/hooks";
import { play } from "../../ui/sound";
import { seatColor } from "../colors";
import { GameLog } from "../GameLog";
import "./snakes.css";

type Jump = "ladder" | "snake";
interface LastRoll { player: string; roll: number; from: number; landed: number; to: number; jump: Jump | null }

interface SnakesView extends GameViewBase {
  players: string[];
  positions: Record<string, number>;
  current: string | null;
  last_roll: LastRoll | null;
  winner: string | null;
  ladders: Record<string, number>;
  snakes: Record<string, number>;
}

type Pt = [number, number];

const DIE_MS = 550; // let the die tumble a little before tokens start moving
const STEP_MS = 190;
const SLIDE_MS = 900;
const FINISH = 100;
/** [light, base, outline] per snake. */
const SNAKE_COLORS: [string, string, string][] = [
  ["#4ade80", "#16a34a", "#14532d"], ["#fb7185", "#e11d48", "#4c0519"], ["#c084fc", "#9333ea", "#3b0764"],
  ["#fbbf24", "#d97706", "#451a03"], ["#22d3ee", "#0891b2", "#083344"], ["#f472b6", "#db2777", "#500724"],
];
const CROWD: Pt[] = [[-2.1, -2.1], [2.1, -2.1], [-2.1, 2.1], [2.1, 2.1]];

/** Board coordinates (0–9, origin bottom-left) for square 1–100, boustrophedon. */
function cell(square: number): { row: number; col: number } {
  const row = Math.floor((square - 1) / 10);
  const offset = (square - 1) % 10;
  return { row, col: row % 2 === 0 ? offset : 9 - offset };
}

/** Square centre in board % (0–100); square 0 waits just off the bottom-left corner. */
function center(square: number): Pt {
  if (square <= 0) return [-4, 95];
  const { row, col } = cell(square);
  return [col * 10 + 5, (9 - row) * 10 + 5];
}

/** A wavy snake from head to tail: C1-smooth cubic segments with alternating bulges. */
function snakeCurve(head: number, tail: number): Pt[][] {
  const [hx, hy] = center(head);
  const [tx, ty] = center(tail);
  const dx = tx - hx, dy = ty - hy, len = Math.hypot(dx, dy) || 1;
  const k = Math.max(2, Math.round(len / 17));
  const amp = Math.min(4.5, (len / k) * 0.55);
  const nx = -dy / len, ny = dx / len;
  return Array.from({ length: k }, (_, i) => {
    const s = i % 2 ? -amp : amp;
    const at = (f: number, bulge: number): Pt =>
      [hx + (dx * (i + f)) / k + nx * bulge, hy + (dy * (i + f)) / k + ny * bulge];
    return [at(0, 0), at(1 / 3, s), at(2 / 3, s), at(1, 0)];
  });
}

const fmt = ([x, y]: Pt) => `${x.toFixed(2)},${y.toFixed(2)}`;
const curvePath = (segs: Pt[][]) =>
  `M${fmt(segs[0]![0]!)}` + segs.map((s) => ` C${fmt(s[1]!)} ${fmt(s[2]!)} ${fmt(s[3]!)}`).join("");

function bezier(seg: Pt[], t: number): Pt {
  const [a, b, c, d] = seg as [Pt, Pt, Pt, Pt];
  const u = 1 - t;
  const f = (i: 0 | 1) => u * u * u * a[i] + 3 * u * u * t * b[i] + 3 * u * t * t * c[i] + t * t * t * d[i];
  return [f(0), f(1)];
}

/** Where a token is, `t` of the way along the ladder or snake from `from` to `to`. */
function alongJump(view: SnakesView, from: number, to: number, t: number): Pt {
  if (view.snakes[from] === to) {
    const segs = snakeCurve(from, to);
    const x = t * segs.length;
    const i = Math.min(segs.length - 1, Math.floor(x));
    return bezier(segs[i]!, x - i);
  }
  const [x1, y1] = center(from);
  const [x2, y2] = center(to);
  return [x1 + (x2 - x1) * t, y1 + (y2 - y1) * t];
}

const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

/** Follows `value`, but waits `ms` before adopting it whenever `key` changes. */
function useLagged<T>(value: T, key: string, ms: number): T {
  // Shows `value` immediately, except that a new roll (`key`) holds it back for `ms` so the
  // die can land first. A pending wait is never restarted, so rapid rolls cannot starve it.
  const [shown, setShown] = useState(value);
  const keyRef = useRef(key);
  const latest = useRef(value);
  latest.current = value;
  const pending = useRef<number | null>(null);
  useEffect(() => {
    if (keyRef.current === key) {
      if (pending.current === null) setShown(value);
      return;
    }
    keyRef.current = key;
    if (pending.current !== null) return;
    pending.current = window.setTimeout(() => {
      pending.current = null;
      setShown(latest.current);
    }, ms);
  }, [value, key, ms]);
  useEffect(() => () => {
    if (pending.current !== null) window.clearTimeout(pending.current);
    pending.current = null;
  }, []);
  return shown;
}

function Ladder({ from, to, hot }: { from: number; to: number; hot: boolean }) {
  const [x1, y1] = center(from);
  const [x2, y2] = center(to);
  const len = Math.hypot(x2 - x1, y2 - y1) || 1;
  const ux = (x2 - x1) / len, uy = (y2 - y1) / len;
  const w = 1.7, nx = -uy * w, ny = ux * w;
  const a: Pt = [x1 - ux * 2.2, y1 - uy * 2.2];
  const b: Pt = [x2 + ux * 2.2, y2 + uy * 2.2];
  const rungs = Math.max(2, Math.floor(len / 3.4));
  const rail = (side: number, cls: string) => (
    <line className={cls} x1={a[0] + nx * side} y1={a[1] + ny * side} x2={b[0] + nx * side} y2={b[1] + ny * side} />
  );
  return (
    <g className={`sl-ladder${hot ? " hot" : ""}`}>
      {hot && <line className="sl-halo" x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} />}
      {Array.from({ length: rungs }, (_, i) => {
        const t = (i + 1) / (rungs + 1);
        const cx = x1 + (x2 - x1) * t, cy = y1 + (y2 - y1) * t;
        return <line key={i} className="sl-rung" x1={cx - nx} y1={cy - ny} x2={cx + nx} y2={cy + ny} />;
      })}
      {rail(-1, "sl-rail")}{rail(1, "sl-rail")}
      {rail(-1, "sl-rail-hi")}{rail(1, "sl-rail-hi")}
    </g>
  );
}

function Snake({ head, tail, index, hot }: { head: number; tail: number; index: number; hot: boolean }) {
  const segs = snakeCurve(head, tail);
  const d = curvePath(segs);
  const [hx, hy] = segs[0]![0]!;
  const [cx, cy] = segs[0]![1]!;
  const [tx, ty] = center(tail);
  const angle = (Math.atan2(hy - cy, hx - cx) * 180) / Math.PI; // the head faces away from the body
  const [light, base, dark] = SNAKE_COLORS[index % SNAKE_COLORS.length]!;
  const id = `sl-snake-grad-${head}`;
  return (
    <g className={`sl-snake${hot ? " hot" : ""}`}>
      <defs>
        <linearGradient id={id} gradientUnits="userSpaceOnUse" x1={hx} y1={hy} x2={tx} y2={ty}>
          <stop offset="0" stopColor={base} />
          <stop offset="1" stopColor={light} />
        </linearGradient>
      </defs>
      {hot && <path className="sl-halo" d={d} />}
      <path className="sl-snake-outline" d={d} stroke={dark} />
      <path className="sl-snake-body" d={d} stroke={`url(#${id})`} />
      <path className="sl-snake-scales" d={d} stroke={dark} />
      <path className="sl-snake-shine" d={d} />
      <g transform={`translate(${hx.toFixed(2)} ${hy.toFixed(2)}) rotate(${angle.toFixed(1)})`}>
        <path className="sl-tongue" d="M1.9 0 H3.4 l0.65 -0.55 M3.4 0 l0.65 0.55" />
        <ellipse cx={0.3} cy={0} rx={2.4} ry={1.85} fill={base} stroke={dark} strokeWidth={0.35} />
        {[-0.85, 0.85].map((ey) => (
          <g key={ey}>
            <circle cx={0.95} cy={ey} r={0.58} fill="#fff" />
            <circle cx={1.15} cy={ey} r={0.3} fill="#0b0f19" />
          </g>
        ))}
      </g>
    </g>
  );
}

function Token({ view, player, target, offset, isTurn }: {
  view: SnakesView; player: string; target: number; offset: Pt; isTurn: boolean;
}) {
  const last = view.last_roll;
  const shown = useStepped(target, (from, to) => {
    if (!last || last.player !== player || last.from !== from || last.to !== to) return [to];
    const steps: number[] = [];
    for (let s = from + 1; s <= last.landed; s++) steps.push(s);
    if (last.jump) steps.push(last.landed, to); // a short pause on the ladder foot / snake head
    return steps.length > 0 ? steps : [to];
  }, STEP_MS);

  const previous = useRef(shown);
  const [slide, setSlide] = useState<{ from: number; to: number; t: number } | null>(null);
  useEffect(() => {
    const before = previous.current;
    previous.current = shown;
    if (!last?.jump || last.player !== player || before !== last.landed || shown !== last.to) return;
    play(last.jump);
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / SLIDE_MS);
      setSlide(t < 1 ? { from: before, to: shown, t: easeInOut(t) } : null);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(frame); setSlide(null); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown]);

  if (target <= 0) return null;
  const [x, y] = slide ? alongJump(view, slide.from, slide.to, slide.t) : center(shown);
  const name = view.names[player] ?? "?";
  const style = { left: `${x + offset[0]}%`, top: `${y + offset[1]}%`, "--c": seatColor(view, player) } as CSSProperties;
  return (
    <div className={`sl-token${isTurn ? " turn" : ""}${slide ? " sliding" : ""}${offset[0] || offset[1] ? " crowded" : ""}`}
      style={style}
      title={`${nameOf(view, player)} · square ${target}`}>
      <span key={shown} className="sl-token-ball">{[...name][0]?.toUpperCase()}</span>
    </div>
  );
}

function rollSummary(view: SnakesView, last: LastRoll | null): { title: string; detail: string } {
  if (!last) return { title: "No rolls yet", detail: "Roll the die to enter the board." };
  const title = `${nameOf(view, last.player)} rolled ${last.roll}`;
  if (last.jump === "ladder") return { title, detail: `Ladder! ${last.landed} → ${last.to}` };
  if (last.jump === "snake") return { title, detail: `Snake! ${last.landed} → ${last.to}` };
  if (last.landed > FINISH) return { title, detail: `Needs exactly ${FINISH - last.from} to finish` };
  return { title, detail: last.to === FINISH ? "Reached 100!" : `Moved to square ${last.to}` };
}

export function SnakesGame({ view, act }: GameProps<SnakesView>) {
  const myTurn = view.current === view.you && !view.winner;
  useTurnAlert(myTurn);
  const last = view.last_roll;
  const rollKey = last ? `${last.player}:${last.from}:${last.roll}:${last.to}` : "";
  const positions = useLagged(view.positions, rollKey, DIE_MS);
  const [busy, setBusy] = useState(false);

  const firstKey = useRef(rollKey);
  useEffect(() => {
    if (rollKey && rollKey !== firstKey.current) play("dice");
    firstKey.current = rollKey;
  }, [rollKey]);

  const steps = last ? Math.max(0, last.landed - last.from) : 0;
  const landDelay = DIE_MS + steps * STEP_MS;
  const flash = useFlash(rollKey, landDelay + (last?.jump ? SLIDE_MS + 1600 : 1600));

  const roll = () => {
    if (!myTurn || busy) return;
    setBusy(true);
    act({ type: "roll" }).catch(() => {}).finally(() => setBusy(false));
  };
  const rollRef = useRef(roll);
  rollRef.current = roll;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (e.key.toLowerCase() !== "r" || e.repeat || e.metaKey || e.ctrlKey || e.altKey || el?.closest("input, textarea, select")) return;
      rollRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onBoard = view.players.filter((p) => (positions[p] ?? 0) > 0);
  const waiting = view.players.filter((p) => (positions[p] ?? 0) === 0);
  const offsetOf = (p: string): Pt => {
    const group = onBoard.filter((q) => positions[q] === positions[p]);
    if (group.length < 2) return [0, 0];
    const i = group.indexOf(p);
    return group.length === 2 ? [i ? 2.2 : -2.2, 0] : CROWD[i % CROWD.length]!;
  };
  const hotJump = flash && last?.jump ? last.landed : null;
  const summary = rollSummary(view, last);
  const status = view.winner ? `${nameOf(view, view.winner)} won!`
    : myTurn ? "Your turn — roll the die!" : `${nameOf(view, view.current)}'s turn`;

  return (
    <div className="game snakes game-layout">
      <div className="sl-main">
        <div className="sl-frame">
          <div className={`sl-board${flash ? " flash" : ""}`}
            style={{ "--land-delay": `${landDelay}ms`, "--dest-delay": `${landDelay + SLIDE_MS}ms` } as CSSProperties}>
            <div className="sl-tiles">
              {Array.from({ length: 100 }, (_, i) => {
                const n = i + 1;
                const { row, col } = cell(n);
                const cls = ["sl-cell", (row + col) % 2 ? "alt" : "",
                  n === 1 ? "start" : "", n === FINISH ? "goal" : "",
                  flash && last && n === last.landed ? "landed" : "",
                  flash && last?.jump && n === last.to ? "dest" : ""].filter(Boolean).join(" ");
                return (
                  <div key={n} className={cls} style={{ gridRow: 10 - row, gridColumn: col + 1 }}>
                    <span className="sl-num">{n}</span>
                    {n === 1 && <span className="sl-tag">Start</span>}
                    {n === FINISH && <Icon name="crown" className="sl-crown" />}
                  </div>
                );
              })}
            </div>
            <svg className={`sl-overlay${hotJump ? " has-hot" : ""}`} viewBox="0 0 100 100" aria-hidden="true">
              <defs>
                <filter id="sl-drop" x="-10%" y="-10%" width="120%" height="120%">
                  <feDropShadow dx="0.35" dy="0.7" stdDeviation="0.45" floodColor="#0b0f19" floodOpacity="0.4" />
                </filter>
              </defs>
              <g filter="url(#sl-drop)">
                {Object.entries(view.ladders).map(([from, to]) => (
                  <Ladder key={from} from={Number(from)} to={to} hot={hotJump === Number(from)} />
                ))}
                {Object.entries(view.snakes).map(([from, to], i) => (
                  <Snake key={from} head={Number(from)} tail={to} index={i} hot={hotJump === Number(from)} />
                ))}
              </g>
            </svg>
            <div className="sl-token-layer">
              {view.players.map((p) => (
                <Token key={p} view={view} player={p} target={positions[p] ?? 0} offset={offsetOf(p)}
                  isTurn={p === view.current && !view.winner} />
              ))}
            </div>
          </div>
        </div>
        {waiting.length > 0 && (
          <div className="sl-waiting">
            <span className="muted">Waiting at the start:</span>
            {waiting.map((p) => (
              <span key={p} className="pill">
                <span className="sl-swatch" style={{ "--c": seatColor(view, p) } as CSSProperties} />
                {nameOf(view, p)}
              </span>
            ))}
          </div>
        )}
      </div>

      <aside className="side-panel">
        <p className={`game-status${myTurn ? " mine" : ""}${view.winner ? " over" : ""}`}>
          <Icon name={view.winner ? "trophy" : myTurn ? "sparkle" : "clock"} />
          {status}
        </p>
        <div className="dice-box sl-dice">
          <Die value={last?.roll ?? null} rollKey={rollKey} size={58} />
          <div className="dice-text" key={rollKey}>
            <strong>{summary.title}</strong>
            <span className={`sl-detail ${last?.jump ?? ""}`}>{summary.detail}</span>
          </div>
        </div>
        <button className="large block" disabled={!myTurn || busy} onClick={roll}>Roll the die</button>
        {myTurn && <p className="sl-hint muted">Tip: press <span className="kbd">R</span> to roll</p>}

        <h3>Players</h3>
        <ul className="player-list">
          {view.players.map((p) => {
            const pos = positions[p] ?? 0;
            const color = seatColor(view, p);
            const turn = p === view.current && !view.winner;
            return (
              <li key={p} className={`player-row${turn ? " is-turn" : ""}`}>
                <Avatar name={view.names[p] ?? "?"} size={34} ring={turn} />
                <div className="grow">
                  <div><span className="sl-swatch" style={{ "--c": color } as CSSProperties} />{nameOf(view, p)}</div>
                  <div className="sub">{pos > 0 ? `Square ${pos}` : "Not on the board yet"}</div>
                  <div className="sl-progress"><span style={{ width: `${pos}%`, background: color }} /></div>
                </div>
                {view.winner === p ? <Icon name="trophy" className="sl-win-icon" />
                  : turn && <span className="turn-chip">Turn</span>}
              </li>
            );
          })}
        </ul>
        <p className="sl-legend muted">
          <Icon name="flag" size={15} /> Land exactly on 100 to win. Ladders climb up, snakes slide down.
        </p>
        <GameLog view={view} />
      </aside>
    </div>
  );
}
