import { useEffect, useRef, useState, type CSSProperties } from "react";
import { nameOf, type GameProps } from "..";
import type { GameViewBase } from "../../types";
import { GameLog } from "../GameLog";
import { Avatar } from "../../ui/Avatar";
import { Modal } from "../../ui/Feedback";
import { Icon } from "../../ui/Icon";
import { useTurnAlert } from "../../ui/hooks";
import { play as playSound } from "../../ui/sound";
import "./uno.css";

type Color = "red" | "yellow" | "green" | "blue";
const COLORS: Color[] = ["red", "yellow", "green", "blue"];
const HEX: Record<Color, string> = { red: "#ef3340", yellow: "#ffcc1f", green: "#2bb24c", blue: "#2a74e8" };

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

const SYMBOL: Record<Card["kind"], string> = {
  number: "", skip: "⊘", reverse: "⇄", draw2: "+2", wild: "W", wild4: "+4",
};
const KIND_NAME: Record<Card["kind"], string> = {
  number: "", skip: "Skip", reverse: "Reverse", draw2: "Draw Two", wild: "Wild", wild4: "Wild Draw Four",
};

const symbolOf = (card: Card) => (card.kind === "number" ? String(card.value) : SYMBOL[card.kind]);
const describe = (card: Card) =>
  card.color === null ? KIND_NAME[card.kind]
    : `${card.color} ${card.kind === "number" ? card.value : KIND_NAME[card.kind]}`;
/** A stable, slightly random tilt per card so the discard pile looks hand-thrown. */
const tiltOf = (id: number) => ((id * 47) % 23) - 11;
const cssVars = (vars: Record<string, string | number>) => vars as CSSProperties;

/** Skip / reverse / wild get drawn glyphs (font symbols render inconsistently across systems). */
const GLYPH: Partial<Record<Card["kind"], string[]>> = {
  skip: ["M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16z", "M6.4 17.6 17.6 6.4"],
  reverse: ["M4 8h14", "M14.5 4.5 18 8l-3.5 3.5", "M20 16H6", "M9.5 12.5 6 16l3.5 3.5"],
  wild: ["M12 2.5l2.6 6.3 6.8.5-5.2 4.4 1.6 6.6L12 16.8l-5.8 3.5 1.6-6.6-5.2-4.4 6.8-.5z"],
};

function Glyph({ card, corner }: { card: Card; corner?: boolean }) {
  const paths = GLYPH[card.kind];
  if (!paths || (corner && card.kind === "wild")) return <>{symbolOf(card)}</>;
  return (
    <svg viewBox="0 0 24 24" className={`uno-glyph uno-glyph-${card.kind}`} aria-hidden="true">
      {paths.map((d) => <path key={d} d={d} />)}
    </svg>
  );
}

function CardFace({ card }: { card: Card }) {
  const sym = symbolOf(card);
  const underline = card.kind === "number" && (card.value === 6 || card.value === 9);
  return (
    <>
      <span className="uno-idx tl" aria-hidden="true"><Glyph card={card} corner /></span>
      <span className={`uno-sym${sym.length > 1 ? " wide" : ""}${underline ? " under" : ""}`} aria-hidden="true">
        <Glyph card={card} />
      </span>
      <span className="uno-idx br" aria-hidden="true"><Glyph card={card} corner /></span>
    </>
  );
}

function CardBack({ style, className = "" }: { style?: CSSProperties; className?: string }) {
  return (
    <span className={`uno-back ${className}`} style={style} aria-hidden="true">
      <span className="uno-wordmark">UNO</span>
    </span>
  );
}

function StaticCard({ card, className = "", style }: { card: Card; className?: string; style?: CSSProperties }) {
  return (
    <div className={`uno-card uno-${card.color ?? "wild"} ${className}`} style={style} role="img" aria-label={describe(card)}>
      <CardFace card={card} />
    </div>
  );
}

export function UnoGame({ view, act, room }: GameProps<UnoView>) {
  const [choosingFor, setChoosingFor] = useState<number | null>(null);
  const [callUno, setCallUno] = useState(false);
  const myTurn = view.current === view.you && !view.winner;
  const me = view.players.find((p) => p.id === view.you);
  const playing = myTurn && view.phase !== "challenge";
  useTurnAlert(myTurn);

  // Keep the previous top card under the new one so plays land on a real pile.
  const [pile, setPile] = useState<{ top: Card; prev: Card | null }>({ top: view.top, prev: null });
  if (pile.top.id !== view.top.id) setPile({ top: view.top, prev: pile.top });

  const myPlay = useRef<number | null>(null);
  const firstTop = useRef(true);
  useEffect(() => {
    if (firstTop.current) { firstTop.current = false; return; }
    if (myPlay.current !== view.top.id) playSound("card");
    myPlay.current = null;
  }, [view.top.id]);

  // Stagger the deal only on first render; later draws pop in on their own.
  const dealt = useRef(false);
  useEffect(() => { dealt.current = true; }, []);

  const send = (action: Record<string, unknown>) => act(action).catch(() => {});
  const play = (cardId: number, color?: Color) => {
    setChoosingFor(null);
    const willHaveOne = view.hand.length === 2;
    myPlay.current = cardId;
    playSound("card");
    void act({ type: "play", card: cardId, color, uno: willHaveOne && callUno })
      .then(() => setCallUno(false), () => { myPlay.current = null; });
  };
  const onCard = (card: Card) => {
    if (!view.playable.includes(card.id)) return;
    if (card.color === null) setChoosingFor(card.id);
    else play(card.id);
  };

  const canDraw = myTurn && view.phase === "play";
  const meIndex = view.players.findIndex((p) => p.id === view.you);
  const opponents = meIndex < 0 ? view.players
    : [...view.players.slice(meIndex + 1), ...view.players.slice(0, meIndex)];
  const online = (id: string) => room.members.find((m) => String(m.session_id) === id)?.online;
  const challenger = view.pending_wd4 ? nameOf(view, view.pending_wd4.by) : "";
  const choosingCard = view.hand.find((c) => c.id === choosingFor);

  const status = view.winner
    ? `${nameOf(view, view.winner)} won!`
    : myTurn
      ? view.phase === "challenge" ? `${challenger} played Wild Draw Four on you` : "Your turn"
      : `${nameOf(view, view.current)}'s turn`;

  const n = view.hand.length;
  const step = n > 1 ? Math.min(5, 44 / (n - 1)) : 0;

  return (
    <div className={`game uno game-layout${myTurn ? " uno-my-turn" : ""}`}>
      <section className="uno-table" style={cssVars({ "--aura": HEX[view.color] })}>
        <div className="uno-seats">
          {opponents.map((p) => {
            const backs = Math.min(p.cards, 7);
            const turn = p.id === view.current && !view.winner;
            return (
              <div key={p.id} className={`uno-seat${turn ? " is-turn" : ""}${p.id === view.winner ? " is-winner" : ""}`}>
                <div className="uno-seat-fan" aria-hidden="true">
                  {Array.from({ length: backs }, (_, i) => (
                    <CardBack key={i} style={cssVars({ "--r": `${(i - (backs - 1) / 2) * 9}deg` })} />
                  ))}
                  {p.cards > 7 && <span className="uno-more">+{p.cards - 7}</span>}
                </div>
                <div className="uno-seat-id">
                  <Avatar name={nameOf(view, p.id)} size={34} ring={turn} online={online(p.id)} />
                  <div>
                    <strong>{nameOf(view, p.id)}</strong>
                    <small>{p.cards} card{p.cards === 1 ? "" : "s"}</small>
                  </div>
                  {p.uno && <span className="uno-badge">UNO</span>}
                  {view.catchable === p.id && <span className="uno-alarm" title="Forgot to call UNO!">!</span>}
                </div>
              </div>
            );
          })}
        </div>

        <div className="uno-center">
          <svg key={view.direction} className={`uno-dir${view.direction === -1 ? " ccw" : ""}`} viewBox="0 0 100 100" aria-hidden="true">
            <path d="M50 6 A44 44 0 0 1 94 50" />
            <path d="M94 50 A44 44 0 0 1 50 94" />
            <path d="M50 94 A44 44 0 0 1 6 50" />
            <path d="M6 50 A44 44 0 0 1 50 6" />
            <path className="head" d="M90 44 L94 52 L98 44" />
            <path className="head" d="M10 56 L6 48 L2 56" />
            <path className="head" d="M44 10 L52 6 L44 2" />
            <path className="head" d="M56 90 L48 94 L56 98" />
          </svg>

          <div className="uno-deck-wrap">
            <button type="button" className={`uno-deck${canDraw ? " can-draw" : ""}`} disabled={!canDraw}
              aria-label="Draw pile" title={canDraw ? "Click to draw" : `${view.deck_count} cards left`}
              onClick={() => void send({ type: "draw" })}>
              <CardBack className="d3" />
              <CardBack className="d2" />
              <CardBack className="d1" />
            </button>
            <span className="pill">{view.deck_count} in deck</span>
          </div>

          <div className="uno-discard-wrap">
            <div className="uno-discard">
              <span className="uno-aura" aria-hidden="true" />
              {pile.prev && (
                <StaticCard card={pile.prev} className="uno-under" style={cssVars({ "--tilt": `${tiltOf(pile.prev.id)}deg` })} />
              )}
              <StaticCard key={view.top.id} card={view.top} className="uno-top"
                style={cssVars({ "--tilt": `${tiltOf(view.top.id)}deg` })} />
            </div>
            <span className="pill">{view.discard_count} played</span>
          </div>

          <div className="uno-meta">
            <span className={`pill uno-colour-pill uno-tint-${view.color}`}>
              <i className="uno-swatch" /> {view.color}
            </span>
            <span key={view.direction} className="pill uno-dir-pill">
              <Icon name={view.direction === 1 ? "refresh" : "rotate"} size={14} />
              {view.direction === 1 ? "Clockwise" : "Counter-clockwise"}
            </span>
          </div>
        </div>

        {myTurn && view.phase === "challenge" && (
          <div className="uno-callout" role="alert">
            <div className="uno-callout-card"><StaticCard card={view.top} /></div>
            <div className="uno-callout-body">
              <strong>{challenger} hit you with a Wild Draw Four</strong>
              <p>Accept and draw 4, or challenge: if they could have matched the colour, they draw 4 instead.
                If the challenge fails, you draw 6.</p>
              <div className="row wrap">
                <button className="warm" onClick={() => void send({ type: "accept" })}>Accept (draw 4)</button>
                <button className="secondary" onClick={() => void send({ type: "challenge" })}>
                  <Icon name="swords" size={16} /> Challenge
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="uno-rail">
          <div className="uno-hand-head">
            <h3>Your hand ({me?.cards ?? view.hand.length})</h3>
            {playing && view.hand.length === 2 && (
              <label className={`uno-call${callUno ? " on" : ""}`}>
                <input type="checkbox" checked={callUno} onChange={(e) => setCallUno(e.target.checked)} />
                <span>Call UNO with this play</span>
              </label>
            )}
          </div>
          <div className={`uno-hand${playing ? " active" : ""}`}>
            {view.hand.map((card, i) => {
              const canPlay = playing && view.playable.includes(card.id);
              const off = i - (n - 1) / 2;
              return (
                <button
                  key={card.id}
                  type="button"
                  className={`uno-card uno-${card.color ?? "wild"}${canPlay ? " uno-playable" : ""}${card.id === view.drawn_card ? " uno-drawn" : ""}`}
                  style={cssVars({
                    "--rot": `${off * step}deg`, "--lift": `${Math.abs(off * step) * 0.9}px`,
                    "--z": i + 1, "--delay": dealt.current ? "0ms" : `${Math.min(i, 12) * 45}ms`,
                  })}
                  disabled={!canPlay}
                  aria-label={describe(card)}
                  onClick={canPlay ? () => onCard(card) : undefined}
                >
                  <CardFace card={card} />
                </button>
              );
            })}
          </div>
        </div>
      </section>

      <aside className="side-panel">
        <p className={`game-status${myTurn ? " mine" : ""}${view.winner ? " over" : ""}`}>
          <Icon name={view.winner ? "trophy" : myTurn ? "sparkle" : "clock"} size={18} />
          {status}
        </p>

        {(canDraw || (myTurn && view.phase === "drawn") || view.catchable === view.you) && (
          <div className="uno-actions">
            {view.catchable === view.you && (
              <button className="warm large block uno-shout" onClick={() => void send({ type: "uno" })}>Call UNO!</button>
            )}
            {canDraw && (
              <button className="block" onClick={() => void send({ type: "draw" })}>
                <Icon name="plus" size={16} /> Draw a card
              </button>
            )}
            {myTurn && view.phase === "drawn" && (
              <button className="secondary block" onClick={() => void send({ type: "pass" })}>Keep it and pass</button>
            )}
          </div>
        )}

        <h3>Players</h3>
        <ul className="player-list">
          {view.players.map((p) => {
            const turn = p.id === view.current && !view.winner;
            return (
              <li key={p.id} className={`player-row${turn ? " is-turn" : ""}`}>
                <Avatar name={nameOf(view, p.id)} size={30} online={online(p.id)} />
                <div className="grow">
                  <div>{nameOf(view, p.id)}{p.uno && <span className="uno-badge sm">UNO</span>}</div>
                  <div className="sub">{p.cards} card{p.cards === 1 ? "" : "s"}{p.id === view.winner ? " · winner" : ""}</div>
                </div>
                {turn && <span className="turn-chip">Turn</span>}
                {view.catchable === p.id && p.id !== view.you && (
                  <button className="small uno-catch" onClick={() => void send({ type: "catch", target: p.id })}>Catch!</button>
                )}
              </li>
            );
          })}
        </ul>
        <GameLog view={view} />
      </aside>

      {choosingFor !== null && (
        <Modal onClose={() => setChoosingFor(null)} labelledBy="uno-pick-title">
          <div className="uno-picker">
            <h2 id="uno-pick-title">Choose a colour</h2>
            <p className="muted">
              {choosingCard ? `Playing ${describe(choosingCard)}` : "Pick the colour to continue with"}
            </p>
            <div className="uno-wheel">
              {COLORS.map((c) => (
                <button key={c} type="button" aria-label={c} className={`uno-wedge uno-${c}`} onClick={() => play(choosingFor, c)}>
                  <span>{c}</span>
                </button>
              ))}
            </div>
            <div className="modal-actions">
              <button className="secondary" onClick={() => setChoosingFor(null)}>Cancel</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
