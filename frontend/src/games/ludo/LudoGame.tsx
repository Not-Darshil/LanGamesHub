import { useEffect, useRef, useState, type CSSProperties } from "react";
import { formatLog, nameOf, type GameProps } from "..";
import type { GameViewBase } from "../../types";
import { Avatar } from "../../ui/Avatar";
import { Die } from "../../ui/Dice";
import { useStepped, useTurnAlert } from "../../ui/hooks";
import { Icon } from "../../ui/Icon";
import { play } from "../../ui/sound";
import { GameLog } from "../GameLog";
import {
  COLORS, HOME_COLUMN, SLOT_POINTS, START_ARROW, TRACK, YARD_AREA, tokenPoint, type Cell, type Color, type Point,
} from "./board";
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

const HOME = 56;
const HOP_MS = 170;
const ROLLED = /\brolled\b/;

// All token progress values as one string ("p1a,p1b,…|p2a,…") so the stepper sees a stable value.
const encode = (view: LudoView) => view.players.map((p) => (view.tokens[p.id] ?? [-1, -1, -1, -1]).join(",")).join("|");
const decode = (s: string): number[][] => (s ? s.split("|").map((row) => row.split(",").map(Number)) : []);
const sameShape = (a: number[][], b: number[][]) => a.length === b.length && a.every((r, i) => r.length === b[i]!.length);

/** Steps a single token square by square when it advanced 1–6; anything else (yard exits, captures) jumps. */
function hopPath(from: string, to: string): string[] {
  const a = decode(from), b = decode(to);
  if (!sameShape(a, b)) return [to];
  let mover: [number, number] | null = null;
  for (let p = 0; p < a.length; p++) {
    for (let i = 0; i < a[p]!.length; i++) {
      const before = a[p]![i]!, after = b[p]![i]!;
      if (before >= 0 && after > before && after - before <= 6) {
        if (mover) return [to];
        mover = [p, i];
      }
    }
  }
  if (!mover) return [to];
  const [p, i] = mover;
  const steps: string[] = [];
  // Captured tokens stay put until the mover lands on them (the final step).
  for (let v = a[p]![i]! + 1; v < b[p]![i]!; v++) {
    const s = a.map((row) => [...row]);
    s[p]![i] = v;
    steps.push(s.map((row) => row.join(",")).join("|"));
  }
  steps.push(to);
  return steps;
}

/** Log entries added between two snapshots of a log that is capped from the front. */
function appended(prev: string[], next: string[]): string[] {
  for (let keep = Math.min(prev.length, next.length); keep > 0; keep--) {
    if (next.slice(0, keep).every((e, i) => e === prev[prev.length - keep + i])) return next.slice(keep);
  }
  return next;
}

// Offsets for tokens sharing a square (2 side by side; 3–4 in a 2×2 grid).
const FAN2: Point[] = [[0, -0.2], [0, 0.2]];
const FAN4: Point[] = [[-0.2, -0.2], [-0.2, 0.2], [0.2, -0.2], [0.2, 0.2]];
const at = ([r, c]: Cell): CSSProperties => ({ gridRow: r + 1, gridColumn: c + 1 });
const pointStyle = ([y, x]: Point, k = 1, extra: Record<string, string | number> = {}) =>
  ({ "--x": x, "--y": y, "--k": k, ...extra }) as CSSProperties;

function Star() {
  return (
    <svg className="lu-star" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5L2.5 9.4l6.6-.9z" />
    </svg>
  );
}

function Arrow({ rotate }: { rotate: number }) {
  return (
    <svg className="lu-arrow" viewBox="0 0 24 24" style={{ transform: `rotate(${rotate}deg)` }} aria-hidden="true">
      <path d="M4 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

/** The static board: yards, track, home columns, start squares, safe stars and the centre. */
function BoardSurface({ view, active }: { view: LudoView; active: Color | null }) {
  const inPlay = new Set(view.players.map((p) => p.color));
  const startOf = new Map(COLORS.map((c) => [view.start[c] ?? -1, c]));
  const safe = new Set(view.safe_squares);
  return (
    <>
      {COLORS.map((color) => {
        const { row, col } = YARD_AREA[color];
        const state = !inPlay.has(color) ? " is-empty" : active === color ? " is-active" : active ? " is-idle" : "";
        return (
          <div key={color} className={`lu-yard lu-c-${color}${state}`}
            style={{ gridRow: `${row + 1} / span 6`, gridColumn: `${col + 1} / span 6` }}>
            {SLOT_POINTS[color].map(([y, x], i) => (
              <span key={i} className="lu-slot" style={{ top: `${((y - row) / 6) * 100}%`, left: `${((x - col) / 6) * 100}%` }} />
            ))}
          </div>
        );
      })}
      {TRACK.map((cell, square) => {
        const start = startOf.get(square);
        return (
          <div key={`t${square}`} className={`lu-cell${start ? ` lu-start lu-c-${start}` : ""}`} style={at(cell)}>
            {start ? <Arrow rotate={START_ARROW[start]} /> : safe.has(square) && <Star />}
          </div>
        );
      })}
      {COLORS.flatMap((color) => HOME_COLUMN[color].map((cell, i) => (
        <div key={`${color}${i}`} className={`lu-cell lu-lane lu-c-${color}`} style={at(cell)} />
      )))}
      <svg className="lu-center" viewBox="0 0 3 3" style={{ gridRow: "7 / span 3", gridColumn: "7 / span 3" }} aria-hidden="true">
        <polygon className="lu-fill-red" points="0,0 0,3 1.5,1.5" />
        <polygon className="lu-fill-green" points="0,0 3,0 1.5,1.5" />
        <polygon className="lu-fill-yellow" points="3,0 3,3 1.5,1.5" />
        <polygon className="lu-fill-blue" points="0,3 3,3 1.5,1.5" />
        <circle cx="1.5" cy="1.5" r="0.32" className="lu-hub" />
      </svg>
    </>
  );
}

export function LudoGame({ view, act }: GameProps<LudoView>) {
  const myTurn = view.current === view.you && !view.winner;
  const canRoll = myTurn && view.phase === "roll";
  const choosing = myTurn && view.phase === "move";
  useTurnAlert(myTurn);

  const target = encode(view);
  const shown = useStepped(target, hopPath, HOP_MS);
  const [hovered, setHovered] = useState<number | null>(null);
  const [burst, setBurst] = useState<{ point: Point; key: number } | null>(null);

  // Sounds and capture bursts as the displayed tokens change.
  const prevShown = useRef(shown);
  useEffect(() => {
    const a = decode(prevShown.current), b = decode(shown);
    prevShown.current = shown;
    if (!sameShape(a, b)) return;
    let captured: Point | null = null, moved = false, left = false;
    for (let p = 0; p < b.length; p++) {
      const player = view.players[p];
      for (let i = 0; i < b[p]!.length; i++) {
        const before = a[p]![i]!, after = b[p]![i]!;
        if (after === before || !player) continue;
        if (after < 0 && before >= 0) captured = tokenPoint(player.color, view.start[player.color], before, i);
        else if (before < 0) left = true;
        else moved = true;
      }
    }
    if (captured) {
      play("capture");
      const point = captured;
      setBurst((old) => ({ point, key: (old?.key ?? 0) + 1 }));
    } else if (left) play("pop");
    else if (moved) play(shown === target ? "move" : "tick");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown]);

  // Tumble the die once per new roll (detected from new "rolled" log entries or a roll→move phase change).
  const [rollKey, setRollKey] = useState(0);
  const [settledKey, setSettledKey] = useState(0);
  const prev = useRef({ log: view.log ?? [], phase: view.phase });
  useEffect(() => {
    const log = view.log ?? [];
    const added = appended(prev.current.log, log);
    const rolled = added.some((e) => ROLLED.test(e)) || (prev.current.phase === "roll" && view.phase === "move");
    prev.current = { log, phase: view.phase };
    if (!rolled) return;
    setRollKey((k) => k + 1);
    play("dice");
  }, [view.version, view.log, view.phase]);

  const rows = decode(shown);
  const shownRows = sameShape(rows, decode(target)) ? rows : decode(target);
  const targetRows = decode(target);

  // Positions for every token, with tokens sharing a square fanned out so each stays visible.
  const pieces = view.players.flatMap((p, pi) => (shownRows[pi] ?? []).map((progress, index) => ({
    player: p, index, progress, point: tokenPoint(p.color, view.start[p.color], progress, index),
    moving: progress !== targetRows[pi]?.[index],
  })));
  const stacks = new Map<string, number[]>();
  pieces.forEach((t, n) => {
    if (t.progress < 0 || t.progress >= HOME) return;
    const k = t.point.join();
    stacks.set(k, [...(stacks.get(k) ?? []), n]);
  });

  const roller = [...(view.log ?? [])].reverse().find((e) => ROLLED.test(e));
  const rolling = settledKey !== rollKey;
  const current = view.players.find((p) => p.id === view.current);
  const ghostToken = choosing && hovered !== null && view.legal_tokens.includes(hovered) && view.roll ? hovered : null;
  const me = view.players.find((p) => p.id === view.you);
  const ghost = ghostToken !== null && me ? (() => {
    const from = view.tokens[me.id]?.[ghostToken] ?? -1;
    return tokenPoint(me.color, view.start[me.color], from < 0 ? 0 : from + view.roll!, ghostToken);
  })() : null;

  const move = (token: number) => {
    setHovered(null);
    void act({ type: "move", token }).catch(() => play("error"));
  };
  const homeCount = (id: string) => (view.tokens[id] ?? []).filter((t) => t === HOME).length;
  const race = (id: string) => (view.tokens[id] ?? []).reduce((sum, t) => sum + Math.max(0, t + 1), 0) / (4 * (HOME + 1));

  return (
    <div className={`game ludo game-layout${myTurn ? " lu-my-turn" : ""}`}>
      <div className="lu-stage">
        <div className="lu-frame">
          <div className="lu-board" aria-label="Ludo board" role="group">
            <BoardSurface view={view} active={view.winner ? null : current?.color ?? null} />
            <div className="lu-layer">
              {ghost && <span className={`lu-ghost lu-c-${me!.color}`} style={pointStyle(ghost)} />}
              {burst && <span key={burst.key} className="lu-burst" style={pointStyle(burst.point)} />}
              {pieces.map((t, n) => {
                const stack = stacks.get(t.point.join()) ?? [n];
                const slot = stack.indexOf(n);
                const fan = (stack.length === 2 ? FAN2 : FAN4)[slot] ?? ([0, 0] as Point);
                const k = t.progress >= HOME ? 0.62 : stack.length > 1 ? 0.7 : t.progress < 0 ? 1.12 : 1;
                const point: Point = stack.length > 1 ? [t.point[0] + fan[0], t.point[1] + fan[1]] : t.point;
                const mine = t.player.id === view.you;
                const movable = choosing && mine && view.legal_tokens.includes(t.index);
                const far = t.progress <= 0 || t.progress >= HOME;
                return (
                  <button
                    key={`${t.player.id}-${t.index}`}
                    type="button"
                    className={`lu-token lu-c-${t.player.color}${movable ? " lu-movable" : ""}${t.moving ? " lu-moving" : ""}${t.progress >= HOME ? " lu-done" : ""}`}
                    style={pointStyle(point, k, { "--dur": far ? "0.5s" : `${HOP_MS + 30}ms` })}
                    disabled={!movable}
                    title={`${nameOf(view, t.player.id)} · token ${t.index + 1}`}
                    aria-label={`${nameOf(view, t.player.id)} ${t.player.color} token ${t.index + 1}${movable ? " — move" : ""}`}
                    onClick={() => move(t.index)}
                    onPointerEnter={() => movable && setHovered(t.index)}
                    onPointerLeave={() => setHovered(null)}
                    onFocus={() => movable && setHovered(t.index)}
                    onBlur={() => setHovered(null)}
                  >
                    <span key={t.progress} className="lu-hop">
                      <span className="lu-pawn">{t.progress >= HOME ? "✓" : ""}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <aside className="side-panel lu-side">
        <p className={`game-status${myTurn ? " mine" : ""}${view.winner ? " over" : ""}`}>
          {view.winner ? <Icon name="trophy" /> : current && <span className={`lu-swatch lu-c-${current.color}`} />}
          {view.winner ? `${nameOf(view, view.winner)} won!` : myTurn
            ? canRoll ? "Your turn — roll the die" : "Choose a token to move"
            : `${nameOf(view, view.current)}'s turn`}
        </p>

        <div className={`dice-box lu-dice${current ? ` lu-c-${current.color}` : ""}${canRoll ? " ready" : ""}`}>
          <Die value={view.roll} rollKey={rollKey} size={64} onSettled={() => setSettledKey(rollKey)} />
          <div className="dice-text">
            {rolling ? <strong>Rolling…</strong> : roller ? (
              <>
                <strong>{formatLog(view, roller)}</strong>
                {view.sixes > 0 && view.phase === "roll" && !view.winner
                  ? <span className="lu-again">Rolled a 6 — roll again!</span>
                  : choosing ? <span>Tap a glowing token</span> : null}
              </>
            ) : <span>{canRoll ? "You start — roll a 6 to leave the yard." : "Waiting for the first roll…"}</span>}
          </div>
        </div>

        <button className="large block lu-roll" disabled={!canRoll} onClick={() => void act({ type: "roll" }).catch(() => play("error"))}>
          Roll the die
        </button>

        <ul className="player-list">
          {view.players.map((p) => {
            const home = homeCount(p.id);
            const isTurn = p.id === view.current && !view.winner;
            return (
              <li key={p.id} className={`player-row lu-player lu-c-${p.color}${isTurn ? " is-turn" : ""}`}>
                <Avatar name={view.names[p.id] ?? "Player"} size={34} ring={isTurn} />
                <div className="grow">
                  <div><span className="lu-swatch" /> {nameOf(view, p.id)}</div>
                  <div className="lu-progress" aria-label={`${home} of 4 tokens home`}>
                    <span className="lu-race" style={{ width: `${race(p.id) * 100}%` }} />
                    <span className="lu-home" style={{ width: `${(home / 4) * 100}%` }} />
                  </div>
                  <div className="sub">{home}/4 home · <span className="lu-cname">{p.color}</span></div>
                </div>
                {view.winner === p.id ? <Icon name="trophy" className="lu-trophy" /> : isTurn && <span className="turn-chip">Turn</span>}
              </li>
            );
          })}
        </ul>

        <p className="muted small-print">A 6 brings a token out and earns another roll. Exact roll to reach home. ★ and start squares are safe.</p>
        <GameLog view={view} />
      </aside>
    </div>
  );
}
