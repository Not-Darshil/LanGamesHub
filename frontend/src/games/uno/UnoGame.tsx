import { useState } from "react";
import { nameOf, type GameProps } from "..";
import type { GameViewBase } from "../../types";
import { GameLog } from "../GameLog";
import "./uno.css";

type Color = "red" | "yellow" | "green" | "blue";
const COLORS: Color[] = ["red", "yellow", "green", "blue"];

interface Card {
  id: number;
  color: Color | null;
  kind: "number" | "skip" | "reverse" | "draw2" | "wild" | "wild4";
  value: number | null;
}

interface UnoView extends GameViewBase {
  players: { id: string; cards: number; uno: boolean }[];
  hand: Card[];
  playable: number[];
  top: Card;
  color: Color;
  direction: 1 | -1;
  current: string;
  phase: "play" | "drawn" | "challenge";
  drawn_card: number | null;
  pending_wd4: { by: string; target: string } | null;
  catchable: string | null;
  deck_count: number;
  discard_count: number;
  winner: string | null;
}

const FACE: Record<Card["kind"], string> = {
  number: "", skip: "⊘", reverse: "⇄", draw2: "+2", wild: "W", wild4: "+4",
};

function CardFace({ card, onClick, playable, small }: {
  card: Card; onClick?: () => void; playable?: boolean; small?: boolean;
}) {
  const label = card.kind === "number" ? String(card.value) : FACE[card.kind];
  return (
    <button
      type="button"
      className={`uno-card uno-${card.color ?? "wild"} ${playable ? "uno-playable" : ""} ${small ? "uno-small" : ""}`}
      onClick={onClick}
      disabled={!onClick}
      title={`${card.color ?? ""} ${card.kind === "number" ? card.value : card.kind}`}
    >
      <span>{label}</span>
    </button>
  );
}

export function UnoGame({ view, act }: GameProps<UnoView>) {
  const [choosingFor, setChoosingFor] = useState<number | null>(null);
  const [callUno, setCallUno] = useState(false);
  const myTurn = view.current === view.you && !view.winner;
  const me = view.players.find((p) => p.id === view.you);

  const play = (cardId: number, color?: Color) => {
    setChoosingFor(null);
    const willHaveOne = view.hand.length === 2;
    void act({ type: "play", card: cardId, color, uno: willHaveOne && callUno })
      .then(() => setCallUno(false), () => {});
  };

  const onCard = (card: Card) => {
    if (!view.playable.includes(card.id)) return;
    if (card.color === null) setChoosingFor(card.id);
    else play(card.id);
  };

  return (
    <div className="game uno">
      <div className="uno-players">
        {view.players.map((p) => (
          <div key={p.id} className={`uno-player ${p.id === view.current ? "uno-current" : ""}`}>
            <strong>{nameOf(view, p.id)}</strong>
            <span className="muted"> {p.cards} card{p.cards === 1 ? "" : "s"}</span>
            {p.uno && <span className="badge">UNO</span>}
            {view.catchable === p.id && p.id !== view.you && (
              <button className="small danger" onClick={() => void act({ type: "catch", target: p.id }).catch(() => {})}>
                Catch!
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="uno-table">
        <div className="uno-pile">
          <CardFace card={view.top} />
          <span className="muted">{view.discard_count} played</span>
        </div>
        <div className="uno-info">
          <p>Colour: <span className={`uno-swatch uno-${view.color}`} /> {view.color}</p>
          <p className="muted">Direction {view.direction === 1 ? "→ clockwise" : "← counter-clockwise"} · {view.deck_count} in deck</p>
          <p className="game-status">
            {view.winner
              ? `${nameOf(view, view.winner)} won!`
              : myTurn
                ? view.phase === "challenge"
                  ? `${nameOf(view, view.pending_wd4?.by)} played Wild Draw Four on you`
                  : "Your turn"
                : `${nameOf(view, view.current)}'s turn`}
          </p>
          {myTurn && view.phase === "play" && (
            <button onClick={() => void act({ type: "draw" }).catch(() => {})}>Draw a card</button>
          )}
          {myTurn && view.phase === "drawn" && (
            <button className="secondary" onClick={() => void act({ type: "pass" }).catch(() => {})}>
              Keep it and pass
            </button>
          )}
          {myTurn && view.phase === "challenge" && (
            <div className="row">
              <button onClick={() => void act({ type: "accept" }).catch(() => {})}>Accept (draw 4)</button>
              <button className="secondary" onClick={() => void act({ type: "challenge" }).catch(() => {})}>
                Challenge
              </button>
            </div>
          )}
          {view.catchable === view.you && (
            <button className="danger" onClick={() => void act({ type: "uno" }).catch(() => {})}>Call UNO!</button>
          )}
        </div>
      </div>

      {choosingFor !== null && (
        <div className="uno-colors">
          Choose a colour:
          {COLORS.map((c) => (
            <button key={c} className={`uno-swatch-btn uno-${c}`} onClick={() => play(choosingFor, c)}>{c}</button>
          ))}
          <button className="secondary small" onClick={() => setChoosingFor(null)}>Cancel</button>
        </div>
      )}

      <div className="uno-hand-head">
        <h3>Your hand ({me?.cards ?? view.hand.length})</h3>
        {myTurn && view.hand.length === 2 && view.phase !== "challenge" && (
          <label className="uno-call">
            <input type="checkbox" checked={callUno} onChange={(e) => setCallUno(e.target.checked)} />
            Call UNO with this play
          </label>
        )}
      </div>
      <div className="uno-hand">
        {view.hand.map((card) => (
          <CardFace
            key={card.id}
            card={card}
            playable={view.playable.includes(card.id)}
            onClick={myTurn && view.playable.includes(card.id) ? () => onCard(card) : undefined}
          />
        ))}
      </div>
      <GameLog view={view} />
    </div>
  );
}
