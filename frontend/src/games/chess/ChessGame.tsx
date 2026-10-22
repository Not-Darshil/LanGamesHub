import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { nameOf, type GameProps } from "..";
import type { GameViewBase } from "../../types";
import { Avatar } from "../../ui/Avatar";
import { useFeedback } from "../../ui/Feedback";
import { useNow, useTurnAlert } from "../../ui/hooks";
import { Icon } from "../../ui/Icon";
import { play } from "../../ui/sound";
import { GameLog } from "../GameLog";
import "./chess.css";

type Side = "white" | "black";

interface ChessClock {
  control: string;
  label: string;
  initial_ms: number;
  increment_ms: number;
  remaining: Record<Side, number>;
  running: Side | null;
}

interface ChessView extends GameViewBase {
  players: string[];
  colors: Record<string, Side>;
  fen: string;
  san: string[];
  turn: Side;
  to_move: string;
  check: boolean;
  last_move: string | null;
  legal_moves: string[];
  draw_offer: string | null;
  can_claim_draw: boolean;
  result: { winners: string[]; draw: boolean; reason: string } | null;
  clock?: ChessClock | null;
}

// Filled glyphs for both colours (styled by CSS); U+FE0E forces text, not emoji, rendering.
const GLYPH: Record<string, string> = { k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
const glyph = (piece: string) => `${GLYPH[piece.toLowerCase()] ?? ""}︎`;
const FILES = "abcdefgh";
const VALUES: Record<string, number> = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };
const START_COUNT: Record<string, number> = { p: 8, n: 2, b: 2, r: 2, q: 1 };
const THEMES = ["wood", "ocean", "emerald", "midnight"] as const;
type Theme = (typeof THEMES)[number];

/** Piece placement from FEN: square name (e.g. "e4") → piece letter. */
function placement(fen: string): Map<string, string> {
  const board = new Map<string, string>();
  const rows = (fen.split(" ")[0] ?? "").split("/");
  rows.forEach((row, i) => {
    let file = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) file += Number(ch);
      else board.set(`${FILES[file++]}${8 - i}`, ch);
    }
  });
  return board;
}

const isWhite = (piece: string) => piece === piece.toUpperCase();

/** Pieces each side has lost, and the material balance from White's point of view. */
function material(pieces: Map<string, string>) {
  const count: Record<string, number> = {};
  for (const p of pieces.values()) count[p] = (count[p] ?? 0) + 1;
  const lost = (side: Side) =>
    Object.entries(START_COUNT).flatMap(([t, n]) => {
      const have = count[side === "white" ? t.toUpperCase() : t] ?? 0;
      return Array<string>(Math.max(0, n - have)).fill(t);
    });
  let balance = 0;
  for (const [p, n] of Object.entries(count)) balance += (isWhite(p) ? 1 : -1) * (VALUES[p.toLowerCase()] ?? 0) * n;
  return { lostWhite: lost("white"), lostBlack: lost("black"), balance };
}

function readTheme(): Theme {
  try {
    const t = window.localStorage.getItem("lgh-chess-theme") as Theme | null;
    return t && THEMES.includes(t) ? t : "wood";
  } catch {
    return "wood";
  }
}

function formatClock(ms: number): string {
  const total = Math.max(0, ms);
  if (total < 20_000) return `0:${(total / 1000).toFixed(1).padStart(4, "0")}`;
  const seconds = Math.ceil(total / 1000);
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

export function ChessGame({ view, act }: GameProps<ChessView>) {
  const { confirm } = useFeedback();
  const [selected, setSelected] = useState<string | null>(null);
  const [promotion, setPromotion] = useState<{ from: string; to: string } | null>(null);
  const [flipped, setFlipped] = useState(false);
  const [theme, setTheme] = useState<Theme>(readTheme);
  const [drag, setDrag] = useState<{ from: string; x: number; y: number; size: number; moved: boolean } | null>(null);
  const [hideOverlay, setHideOverlay] = useState(false);
  const skipAnim = useRef<string | null>(null);
  const boardRef = useRef<HTMLDivElement>(null);
  const movesRef = useRef<HTMLOListElement>(null);

  const myColor: Side = view.colors[view.you] ?? "white";
  const pieces = useMemo(() => placement(view.fen), [view.fen]);
  const myTurn = view.legal_moves.length > 0;
  const bottom: Side = flipped ? (myColor === "white" ? "black" : "white") : myColor;
  const ranks = bottom === "white" ? [8, 7, 6, 5, 4, 3, 2, 1] : [1, 2, 3, 4, 5, 6, 7, 8];
  const files = bottom === "white" ? [...FILES] : [...FILES].reverse();
  const targetsFrom = (from: string | null) =>
    new Set(from ? view.legal_moves.filter((m) => m.startsWith(from)).map((m) => m.slice(2, 4)) : []);
  const targets = targetsFrom(drag?.from ?? selected);
  const kingSquare = view.check
    ? [...pieces.entries()].find(([, p]) => p === (view.turn === "white" ? "K" : "k"))?.[0]
    : undefined;
  const { lostWhite, lostBlack, balance } = material(pieces);

  useTurnAlert(myTurn);

  // Clear a stale selection when the position changes.
  useEffect(() => {
    setSelected(null);
    setPromotion(null);
  }, [view.fen]);

  // Move sounds, and keep the move list scrolled to the latest move.
  const lastFen = useRef(view.fen);
  useEffect(() => {
    const before = lastFen.current;
    lastFen.current = view.fen;
    if (before === view.fen) return;
    const captured = placement(before).size > pieces.size;
    play(view.check ? "check" : captured ? "capture" : "move");
    movesRef.current?.scrollTo({ top: movesRef.current.scrollHeight, behavior: "smooth" });
  }, [view.fen, view.check, pieces.size]);

  useEffect(() => setHideOverlay(false), [view.result]);

  const send = (uci: string, fromDrag = false) => {
    setSelected(null);
    setPromotion(null);
    skipAnim.current = fromDrag ? uci.slice(0, 4) : null;
    void act({ type: "move", uci }).catch(() => {});
  };

  const tryMove = (from: string, to: string, fromDrag = false): boolean => {
    if (!targetsFrom(from).has(to)) return false;
    const options = view.legal_moves.filter((m) => m.startsWith(from + to));
    if (options.some((m) => m.length === 5)) {
      setPromotion({ from, to });
      setSelected(from);
    } else send(from + to, fromDrag);
    return true;
  };

  const isMine = (square: string) => {
    const piece = pieces.get(square);
    return !!piece && isWhite(piece) === (myColor === "white") && view.legal_moves.some((m) => m.startsWith(square));
  };

  const onSquare = (square: string) => {
    if (!myTurn || promotion) return;
    if (selected && tryMove(selected, square)) return;
    setSelected(isMine(square) && selected !== square ? square : null);
  };

  // Drag and drop on top of click-click moves (pointer events cover mouse and touch).
  const onPointerDown = (event: ReactPointerEvent, square: string) => {
    if (!myTurn || promotion || event.button !== 0) return;
    if (selected && selected !== square && tryMove(selected, square)) return;
    if (!isMine(square)) {
      setSelected(null);
      return;
    }
    const size = boardRef.current ? boardRef.current.getBoundingClientRect().width / 8 : 60;
    setSelected(square);
    setDrag({ from: square, x: event.clientX, y: event.clientY, size, moved: false });
  };

  useEffect(() => {
    if (!drag) return;
    const move = (e: PointerEvent) => setDrag((d) => d && {
      ...d, x: e.clientX, y: e.clientY, moved: d.moved || Math.hypot(e.clientX - d.x, e.clientY - d.y) > 4,
    });
    const up = (e: PointerEvent) => {
      const el = document.elementFromPoint(e.clientX, e.clientY)?.closest<HTMLElement>(".ch-square");
      const to = el?.getAttribute("aria-label");
      setDrag((d) => {
        if (d && to && to !== d.from && d.moved) tryMove(d.from, to, true);
        return null;
      });
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drag?.from]);

  // Slide animation for the last move (and the rook when castling).
  const anim = new Map<string, { dx: number; dy: number }>();
  if (view.last_move && skipAnim.current !== view.last_move.slice(0, 4)) {
    const col = (sq: string) => files.indexOf(sq[0]!);
    const row = (sq: string) => ranks.indexOf(Number(sq[1]));
    const add = (from: string, to: string) => anim.set(to, { dx: col(from) - col(to), dy: row(from) - row(to) });
    const from = view.last_move.slice(0, 2);
    const to = view.last_move.slice(2, 4);
    add(from, to);
    const moved = pieces.get(to);
    if (moved?.toLowerCase() === "k" && Math.abs(FILES.indexOf(from[0]!) - FILES.indexOf(to[0]!)) === 2) {
      const rank = to[1]!;
      if (to[0] === "g") add(`h${rank}`, `f${rank}`);
      else add(`a${rank}`, `d${rank}`);
    }
  }

  const status = view.result
    ? view.result.draw ? `Draw — ${view.result.reason}` : `${nameOf(view, view.result.winners[0])} won — ${view.result.reason}`
    : myTurn ? `Your move (${myColor})${view.check ? " — you are in check!" : ""}`
    : `${nameOf(view, view.to_move)} to move${view.check ? " (in check)" : ""}`;

  const call = (type: string) => () => void act({ type }).catch(() => {});
  const resign = async () => {
    const ok = await confirm({ title: "Resign this game?", body: "Your opponent will be declared the winner.", confirmLabel: "Resign", danger: true });
    if (ok) call("resign")();
  };
  const changeTheme = () => {
    const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length]!;
    setTheme(next);
    try {
      window.localStorage.setItem("lgh-chess-theme", next);
    } catch {
      /* preference only */
    }
  };

  const topSide: Side = bottom === "white" ? "black" : "white";
  const playerFor = (side: Side) => view.players.find((p) => view.colors[p] === side) ?? null;
  const bar = (side: Side) => {
    const player = playerFor(side);
    const lost = side === "white" ? lostBlack : lostWhite; // pieces this side has captured
    const advantage = side === "white" ? balance : -balance;
    return (
      <PlayerBar name={nameOf(view, player)} realName={player ? view.names[player] ?? "Player" : "Player"} side={side}
        active={!view.result && view.turn === side} captured={lost} advantage={advantage}
        clock={view.clock ?? null} isMe={player === view.you} over={!!view.result} />
    );
  };

  const moveRows = Array.from({ length: Math.ceil(view.san.length / 2) }, (_, i) => [view.san[2 * i], view.san[2 * i + 1]] as const);
  const result = view.result;
  const iWon = result && !result.draw && result.winners.includes(view.you);

  return (
    <div className="game chess game-layout">
      <div className="ch-main">
        {bar(topSide)}
        <div className={`ch-board-frame theme-${theme}${myTurn ? " my-turn" : ""}`}>
          <div className="ch-board" ref={boardRef} onContextMenu={(e) => e.preventDefault()}>
            {ranks.map((rank) =>
              files.map((file) => {
                const square = `${file}${rank}`;
                const piece = pieces.get(square);
                // a1 is a dark square: (file index + rank) is odd for dark squares.
                const dark = (FILES.indexOf(file) + rank) % 2 === 1;
                const motion = anim.get(square);
                const classes = [
                  "ch-square", dark ? "ch-dark" : "ch-light",
                  selected === square && "ch-selected",
                  targets.has(square) && (piece ? "ch-capture" : "ch-target"),
                  view.last_move && (view.last_move.slice(0, 2) === square || view.last_move.slice(2, 4) === square) && "ch-last",
                  kingSquare === square && "ch-check",
                  isMine(square) && myTurn && "ch-movable",
                ].filter(Boolean).join(" ");
                return (
                  <button key={square} type="button" className={classes} aria-label={square}
                    onPointerDown={(e) => onPointerDown(e, square)}
                    onClick={(e) => { if (e.detail === 0) onSquare(square); }}
                    disabled={!myTurn}>
                    {piece && (
                      <span key={motion ? `${view.last_move}` : "still"}
                        className={`ch-piece ${isWhite(piece) ? "ch-white" : "ch-black"}${motion ? " ch-anim" : ""}${drag?.from === square && drag.moved ? " ch-dragging" : ""}`}
                        style={motion ? { ["--dx" as string]: motion.dx, ["--dy" as string]: motion.dy } : undefined}>
                        {glyph(piece)}
                      </span>
                    )}
                    {file === files[0] && <span className="ch-rank">{rank}</span>}
                    {rank === ranks[ranks.length - 1] && <span className="ch-file">{file}</span>}
                  </button>
                );
              }),
            )}
            {promotion && (
              <div className="ch-promo" style={{ left: `${files.indexOf(promotion.to[0]!) * 12.5}%`, ...(ranks.indexOf(Number(promotion.to[1])) === 0 ? { top: 0 } : { bottom: 0, flexDirection: "column-reverse" }) }}>
                {(["q", "r", "b", "n"] as const).map((p) => (
                  <button key={p} type="button" aria-label={`Promote to ${({ q: "queen", r: "rook", b: "bishop", n: "knight" })[p]}`}
                    onClick={() => send(promotion.from + promotion.to + p)}>
                    <span className={`ch-piece ${myColor === "white" ? "ch-white" : "ch-black"}`}>{glyph(p)}</span>
                  </button>
                ))}
                <button type="button" className="ch-promo-cancel" aria-label="Cancel promotion" onClick={() => { setPromotion(null); setSelected(null); }}>
                  <Icon name="x" size={16} />
                </button>
              </div>
            )}
            {result && !hideOverlay && (
              <div className="ch-over" onClick={() => setHideOverlay(true)}>
                <div className="ch-over-card">
                  <span className="ch-over-icon">{result.draw ? "🤝" : iWon ? "🏆" : "♚︎"}</span>
                  <strong>{result.draw ? "Draw" : iWon ? "You won!" : `${nameOf(view, result.winners[0])} won`}</strong>
                  <span>{result.reason}</span>
                  <small>Click to view the board</small>
                </div>
              </div>
            )}
          </div>
          {drag?.moved && (
            <span className={`ch-ghost ch-piece ${isWhite(pieces.get(drag.from) ?? "P") ? "ch-white" : "ch-black"}`}
              style={{ left: drag.x, top: drag.y, width: drag.size, height: drag.size, fontSize: drag.size * 0.82 }}>
              {glyph(pieces.get(drag.from) ?? "p")}
            </span>
          )}
        </div>
        {bar(bottom)}
      </div>

      <aside className="side-panel ch-side">
        <p className={`game-status${myTurn ? " mine" : ""}${result ? " over" : ""}`}>
          <span className={`ch-turn-dot ${view.turn}`} />{status}
        </p>
        <div className="row wrap">
          <span className="pill"><Icon name="clock" size={13} />{view.clock ? view.clock.label : "No clock"}</span>
          {view.clock && !view.clock.running && !result && view.san.length === 0 && <span className="pill accent">Clocks start after White's first move</span>}
        </div>

        {!result && view.draw_offer && view.draw_offer !== view.you && (
          <div className="ch-offer">
            <Icon name="handshake" size={20} />
            <span className="grow"><strong>{nameOf(view, view.draw_offer)}</strong> offers a draw</span>
            <button className="small success" onClick={call("accept_draw")}>Accept draw</button>
            <button className="small secondary" onClick={call("decline_draw")}>Decline</button>
          </div>
        )}
        {!result && (
          <div className="ch-actions">
            {view.draw_offer === view.you ? (
              <span className="pill accent">Draw offered…</span>
            ) : (
              <button className="secondary small" disabled={!!view.draw_offer} onClick={call("offer_draw")}>
                <Icon name="handshake" size={15} />Offer draw
              </button>
            )}
            {view.can_claim_draw && <button className="secondary small" onClick={call("claim_draw")}>Claim draw</button>}
            <button className="danger small" onClick={() => void resign()}><Icon name="flag" size={15} />Resign</button>
          </div>
        )}

        <div className="ch-moves-head">
          <h3>Moves</h3>
          <span className="row" style={{ gap: 4 }}>
            <button className="ghost icon-btn small" title="Flip board" aria-label="Flip board" onClick={() => setFlipped(!flipped)}><Icon name="flip" size={16} /></button>
            <button className="ghost icon-btn small" title={`Board theme: ${theme}`} aria-label="Change board theme" onClick={changeTheme}><Icon name="settings" size={16} /></button>
          </span>
        </div>
        <ol className="ch-moves" ref={movesRef}>
          {moveRows.length === 0 && <li className="ch-moves-empty">No moves yet</li>}
          {moveRows.map(([w, b], i) => (
            <li key={i}>
              <span className="ch-move-no">{i + 1}.</span>
              <span className={!b && i === moveRows.length - 1 ? "latest" : ""}>{w}</span>
              <span className={b && i === moveRows.length - 1 ? "latest" : ""}>{b ?? ""}</span>
            </li>
          ))}
        </ol>
        <GameLog view={view} />
      </aside>
    </div>
  );
}

function PlayerBar({ name, realName, side, active, captured, advantage, clock, isMe, over }: {
  name: string; realName: string; side: Side; active: boolean; captured: string[]; advantage: number;
  clock: ChessClock | null; isMe: boolean; over: boolean;
}) {
  const order = ["q", "r", "b", "n", "p"];
  const sorted = [...captured].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  return (
    <div className={`ch-player${active ? " active" : ""}`}>
      <Avatar name={realName} size={38} ring={active} />
      <div className="ch-player-info">
        <div className="ch-player-name">
          {name}{isMe && name !== "You" ? " (you)" : ""}
          <span className={`ch-side-chip ${side}`}>{side}</span>
        </div>
        <div className="ch-captured" aria-label={`Captured: ${sorted.join(", ") || "none"}`}>
          {sorted.map((p, i) => <span key={i} className={side === "white" ? "cap-black" : "cap-white"}>{glyph(p)}</span>)}
          {advantage > 0 && <em>+{advantage}</em>}
        </div>
      </div>
      {clock && <ChessClockFace clock={clock} side={side} isMe={isMe} over={over} />}
    </div>
  );
}

function ChessClockFace({ clock, side, isMe, over }: { clock: ChessClock; side: Side; isMe: boolean; over: boolean }) {
  const running = clock.running === side && !over;
  // The server sent the time left when this view was built; count down locally from there.
  const syncedAt = useMemo(() => performance.now(), [clock]);
  const now = useNow(running, 100);
  const elapsed = running ? Math.max(0, now - syncedAt) : 0;
  const left = Math.max(0, clock.remaining[side] - elapsed);
  const low = left < Math.min(20_000, clock.initial_ms * 0.1);
  const second = Math.ceil(left / 1000);
  const lastSecond = useRef(second);
  useEffect(() => {
    if (running && isMe && low && second !== lastSecond.current && second > 0) play("tick");
    lastSecond.current = second;
  }, [second, running, isMe, low]);
  const pct = Math.min(100, (left / clock.initial_ms) * 100);
  return (
    <div className={`ch-clock${running ? " running" : ""}${low ? " low" : ""}${left === 0 ? " flagged" : ""}`} role="timer" aria-label={`${side} clock`}>
      <span className="ch-clock-time">{formatClock(left)}</span>
      <span className="ch-clock-bar"><span style={{ width: `${pct}%` }} /></span>
    </div>
  );
}
