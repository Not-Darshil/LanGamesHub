import { useState } from "react";
import { nameOf, type GameProps } from "..";
import type { GameViewBase } from "../../types";
import { GameLog } from "../GameLog";
import "./chess.css";

interface ChessView extends GameViewBase {
  players: string[];
  colors: Record<string, "white" | "black">;
  fen: string;
  san: string[];
  turn: "white" | "black";
  to_move: string;
  check: boolean;
  last_move: string | null;
  legal_moves: string[];
  draw_offer: string | null;
  can_claim_draw: boolean;
  result: { winners: string[]; draw: boolean; reason: string } | null;
}

const GLYPHS: Record<string, string> = {
  K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙",
  k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟",
};
const FILES = "abcdefgh";

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

export function ChessGame({ view, act }: GameProps<ChessView>) {
  const [selected, setSelected] = useState<string | null>(null);
  const [promotion, setPromotion] = useState<{ from: string; to: string } | null>(null);
  const myColor = view.colors[view.you] ?? "white";
  const pieces = placement(view.fen);
  const myTurn = view.legal_moves.length > 0;
  const targets = new Set(
    selected ? view.legal_moves.filter((m) => m.startsWith(selected)).map((m) => m.slice(2, 4)) : [],
  );
  const kingSquare = view.check
    ? [...pieces.entries()].find(([, p]) => p === (view.turn === "white" ? "K" : "k"))?.[0]
    : undefined;
  const opponent = view.players.find((p) => p !== view.you) ?? null;

  const ranks = myColor === "white" ? [8, 7, 6, 5, 4, 3, 2, 1] : [1, 2, 3, 4, 5, 6, 7, 8];
  const files = myColor === "white" ? [...FILES] : [...FILES].reverse();

  const send = (uci: string) => {
    setSelected(null);
    setPromotion(null);
    void act({ type: "move", uci }).catch(() => {});
  };

  const onSquare = (square: string) => {
    if (!myTurn) return;
    if (selected && targets.has(square)) {
      const options = view.legal_moves.filter((m) => m.startsWith(selected + square));
      if (options.some((m) => m.length === 5)) setPromotion({ from: selected, to: square });
      else send(selected + square);
      return;
    }
    const piece = pieces.get(square);
    const mine = piece && (piece === piece.toUpperCase()) === (myColor === "white");
    setSelected(mine && view.legal_moves.some((m) => m.startsWith(square)) ? square : null);
  };

  const status = view.result
    ? view.result.draw ? `Draw — ${view.result.reason}` : `${nameOf(view, view.result.winners[0])} won — ${view.result.reason}`
    : myTurn ? `Your move (${myColor})${view.check ? " — you are in check!" : ""}`
    : `${nameOf(view, view.to_move)} to move${view.check ? " (in check)" : ""}`;

  const call = (type: string) => () => void act({ type }).catch(() => {});

  return (
    <div className="game chess game-columns">
      <div className="ch-board-wrap">
        <p className="muted">{nameOf(view, opponent)} ({myColor === "white" ? "black" : "white"})</p>
        <div className="ch-board">
          {ranks.map((rank) =>
            files.map((file) => {
              const square = `${file}${rank}`;
              const piece = pieces.get(square);
              // a1 is a dark square: (file index + rank) is odd for dark squares.
              const dark = (FILES.indexOf(file) + rank) % 2 === 1;
              const classes = [
                "ch-square", dark ? "ch-dark" : "ch-light",
                selected === square && "ch-selected",
                targets.has(square) && (piece ? "ch-capture" : "ch-target"),
                view.last_move && (view.last_move.slice(0, 2) === square || view.last_move.slice(2, 4) === square) && "ch-last",
                kingSquare === square && "ch-check",
              ].filter(Boolean).join(" ");
              return (
                <button key={square} type="button" className={classes} aria-label={square}
                  onClick={() => onSquare(square)} disabled={!myTurn}>
                  {piece && <span className={`ch-piece ${piece === piece.toUpperCase() ? "ch-white" : "ch-black"}`}>{GLYPHS[piece]}</span>}
                  {file === files[0] && <span className="ch-rank">{rank}</span>}
                  {rank === ranks[ranks.length - 1] && <span className="ch-file">{file}</span>}
                </button>
              );
            }),
          )}
        </div>
        <p className="muted">{nameOf(view, view.you)} ({myColor})</p>
      </div>

      <div className="ch-side">
        <p className="game-status">{status}</p>
        {promotion && (
          <div className="row ch-promo">
            Promote to:
            {(["q", "r", "b", "n"] as const).map((p) => (
              <button key={p} className="secondary" onClick={() => send(promotion.from + promotion.to + p)}>
                {GLYPHS[myColor === "white" ? p.toUpperCase() : p]}
              </button>
            ))}
            <button className="secondary small" onClick={() => setPromotion(null)}>Cancel</button>
          </div>
        )}
        {!view.result && (
          <div className="row wrap">
            {view.draw_offer && view.draw_offer !== view.you ? (
              <>
                <span className="notice">{nameOf(view, view.draw_offer)} offers a draw</span>
                <button onClick={call("accept_draw")}>Accept draw</button>
                <button className="secondary" onClick={call("decline_draw")}>Decline</button>
              </>
            ) : view.draw_offer === view.you ? (
              <span className="muted">Draw offered…</span>
            ) : (
              <button className="secondary" onClick={call("offer_draw")}>Offer draw</button>
            )}
            {view.can_claim_draw && <button className="secondary" onClick={call("claim_draw")}>Claim draw</button>}
            <button className="danger" onClick={() => { if (window.confirm("Resign this game?")) call("resign")(); }}>Resign</button>
          </div>
        )}
        <h3 className="ch-moves-title">Moves</h3>
        <ol className="ch-moves">
          {Array.from({ length: Math.ceil(view.san.length / 2) }, (_, i) => (
            <li key={i}>{view.san[2 * i]} {view.san[2 * i + 1] ?? ""}</li>
          ))}
        </ol>
        <GameLog view={view} />
      </div>
    </div>
  );
}
