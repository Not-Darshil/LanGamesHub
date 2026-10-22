import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type RefObject } from "react";
import { nameOf, type GameProps } from "..";
import { Avatar } from "../../ui/Avatar";
import { Die } from "../../ui/Dice";
import { Modal, useFeedback } from "../../ui/Feedback";
import { Icon } from "../../ui/Icon";
import { useNow, useStepped, useTurnAlert } from "../../ui/hooks";
import { play } from "../../ui/sound";
import { seatColor } from "../colors";
import { GameLog } from "../GameLog";
import {
  CODES, HOTEL, ICONS, cellOf, groupsOf, hopPath, isProperty, jailPoint, rupees, tokenPoint, tradable,
  type BizPlayer, type BusinessView, type Square, type Trade, type TradeSide,
} from "./board";
import "./business.css";

const DIE_MS = 750;  // the dice tumble before tokens start moving
const HOP_MS = 150;

type Act = (action: Record<string, unknown>) => Promise<boolean>;

// ---------------------------------------------------------------- small hooks

/** Runs `fn(previous)` whenever `value` changes (not on the first render). */
function useOnChange<T>(value: T, fn: (previous: T) => void): void {
  const prev = useRef(value);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    if (Object.is(prev.current, value)) return;
    const before = prev.current;
    prev.current = value;
    fnRef.current(before);
  }, [value]);
}

/** Follows `value`, but holds it back for `ms` whenever `key` changes (so the dice land first). */
function useLagged<T>(value: T, key: string | number, ms: number): T {
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

/** A number that counts smoothly to its new value. */
function useCountUp(value: number, ms = 700): number {
  const [shown, setShown] = useState(value);
  const current = useRef(value);
  useEffect(() => {
    const from = current.current;
    if (from === value) return;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      const v = Math.round(from + (value - from) * (1 - (1 - t) ** 3));
      current.current = v;
      setShown(v);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, ms]);
  return shown;
}

function useWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => { if (entry) setWidth(entry.contentRect.width); });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

// ---------------------------------------------------------------- helpers

const ordinalHouses = (n: number) => (n === HOTEL ? "Hotel" : `${n} house${n === 1 ? "" : "s"}`);
const nameOrBank = (view: BusinessView, id: string | null) => (id ? nameOf(view, id) : "the bank");

function describeSide(view: BusinessView, side: TradeSide): string {
  const parts = side.squares.map((i) => view.board[i]?.name ?? "?");
  if (side.cash) parts.push(rupees(side.cash));
  return parts.length ? parts.join(", ") : "nothing";
}

function statusText(view: BusinessView, me: BizPlayer | undefined): string {
  if (view.result) {
    const names = view.result.winners.map((w) => nameOf(view, w));
    if (names.length === 0) return "Game over";
    const verb = names.length === 1 && names[0] !== "You" ? "wins" : "win";
    return view.result.reason.startsWith("Time") ? `Time up — ${names.join(" & ")} ${verb}!` : `${names.join(" & ")} ${verb}!`;
  }
  if (me?.bankrupt) return "You are bankrupt — watching the game";
  const current = nameOf(view, view.current);
  if (view.current !== view.you || !view.you) {
    if (view.phase === "buy" && view.offer) return `${current} is deciding on ${view.board[view.offer.square]?.name}`;
    if (view.phase === "debt") return `${current} is settling a debt`;
    return `${current}'s turn`;
  }
  if (view.phase === "roll") return me?.in_jail ? "Your turn — you're in Jail" : view.again ? "Your turn — doubles, roll again!" : "Your turn — roll the dice!";
  if (view.phase === "buy" && view.offer) return `Your turn — buy ${view.board[view.offer.square]?.name}?`;
  if (view.phase === "debt" && view.debt) return `Your turn — you owe ${rupees(view.debt.amount)}`;
  return "Your turn — end it when ready";
}

// ---------------------------------------------------------------- board pieces

function Buildings({ count }: { count: number }) {
  if (!count) return null;
  if (count === HOTEL) return <span className="bz-hotel" title="Hotel" />;
  return <>{Array.from({ length: count }, (_, i) => <span key={i} className="bz-house" />)}</>;
}

function CornerArt({ square, view }: { square: Square; view: BusinessView }) {
  switch (square.kind) {
    case "start":
      return (
        <div className="bz-corner-art bz-start-art">
          <span className="bz-corner-small">Collect {rupees(view.rules.salary)}</span>
          <strong>START</strong>
          <svg viewBox="0 0 60 20" className="bz-start-arrow" aria-hidden="true">
            <path d="M58 10H8M16 2 6 10l10 8" />
          </svg>
        </div>
      );
    case "jail":
      return (
        <div className="bz-corner-art bz-jail-art">
          <div className="bz-jail-cell"><span>JAIL</span></div>
          <span className="bz-visiting">Just visiting</span>
        </div>
      );
    case "rest":
      return (
        <div className="bz-corner-art bz-rest-art">
          <span className="bz-corner-emoji" aria-hidden="true">🏡</span>
          <strong>REST HOUSE</strong>
          <span className="bz-corner-small">Put your feet up</span>
        </div>
      );
    default:
      return (
        <div className="bz-corner-art bz-gojail-art">
          <span className="bz-corner-emoji" aria-hidden="true">🚨</span>
          <strong>GO TO JAIL</strong>
          <span className="bz-corner-small">Do not collect salary</span>
        </div>
      );
  }
}

function Tile({ view, square, hot, onOpen }: { view: BusinessView; square: Square; hot: boolean; onOpen: (i: number) => void }) {
  const { row, col, side } = cellOf(square.index);
  const owner = view.owners[square.index] ?? null;
  const houses = view.houses[square.index] ?? 0;
  const mortgaged = !!view.mortgaged[square.index];
  const clickable = isProperty(square);
  const cls = ["bz-tile", `bz-${side}`, `bz-k-${square.kind}`, owner ? "owned" : "", mortgaged ? "mortgaged" : "",
    hot ? "hot" : "", clickable ? "clickable" : ""].filter(Boolean).join(" ");
  const style = {
    gridRow: row + 1, gridColumn: col + 1,
    "--band": square.color ?? "transparent",
    "--owner": owner ? seatColor(view, owner) : "transparent",
  } as CSSProperties;
  const open = () => clickable && onOpen(square.index);
  const onKey = (e: ReactKeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } };
  const label = `${square.name}${owner ? ` · owned by ${nameOf(view, owner)}` : ""}${mortgaged ? " · mortgaged" : ""}`;
  return (
    <div className={cls} style={style} title={label} aria-label={label}
      role={clickable ? "button" : undefined} tabIndex={clickable ? 0 : undefined}
      onClick={open} onKeyDown={clickable ? onKey : undefined}>
      {side === "corner" ? <CornerArt square={square} view={view} /> : (
        <>
          {square.kind === "city" && <div className="bz-band"><Buildings count={houses} /></div>}
          <div className="bz-body">
            {square.kind === "city" ? null : square.kind === "chance"
              ? <span className="bz-chance-mark" aria-hidden="true">?</span>
              : <span className="bz-icon" aria-hidden="true">{ICONS[square.name] ?? "•"}</span>}
            <span className="bz-name">
              <span className="full">{square.name.replace(" Board", "")}</span>
              <span className="code">{CODES[square.name] ?? square.name.replace(" Board", "")}</span>
            </span>
            {square.price != null && <span className="bz-price">{rupees(square.price)}</span>}
            {square.kind === "tax" && <span className="bz-price">Pay {rupees(view.rules.income_tax)}</span>}
          </div>
          {owner && <span className="bz-owner" />}
          {mortgaged && <span className="bz-mort">Mortgaged</span>}
        </>
      )}
    </div>
  );
}

function Token({ view, player, target, jailed, offset, isTurn }: {
  view: BusinessView; player: string; target: number; jailed: boolean; offset: [number, number]; isTurn: boolean;
}) {
  const movesRef = useRef(view.moves);
  movesRef.current = view.moves;
  const shown = useStepped(target, (from, to) => hopPath(movesRef.current, player, from, to), HOP_MS);
  useOnChange(shown, () => play("move"));
  const [x, y] = jailed && shown === view.rules.jail ? jailPoint() : tokenPoint(shown);
  const name = view.names[player] ?? "?";
  const style = { left: `${x + offset[0]}%`, top: `${y + offset[1]}%`, "--c": seatColor(view, player) } as CSSProperties;
  return (
    <div className={`bz-token${isTurn ? " turn" : ""}`} style={style} title={`${nameOf(view, player)} · ${view.board[target]?.name}`}>
      <span key={shown} className="bz-token-ball">{[...name][0]?.toUpperCase()}</span>
    </div>
  );
}

const CROWD: [number, number][] = [[-1.7, -1.4], [1.7, -1.4], [-1.7, 1.4], [1.7, 1.4], [0, -2.6], [0, 2.6]];

// ---------------------------------------------------------------- centre stage

function TimeLeft({ ms, running }: { ms: number; running: boolean }) {
  const synced = useMemo(() => performance.now(), [ms]); // eslint-disable-line react-hooks/exhaustive-deps
  const now = useNow(running, 1000);
  const left = Math.max(0, ms - (running ? now - synced : 0));
  const total = Math.ceil(left / 1000);
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  const text = h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
  return (
    <span className={`bz-timer${left < 5 * 60_000 ? " low" : ""}`} role="timer" aria-label="Time left">
      <Icon name="clock" size={13} /> {text} left
    </span>
  );
}

function MiniDeed({ view, square }: { view: BusinessView; square: Square }) {
  return (
    <div className="bz-mini-deed" style={{ "--band": square.color ?? "#475569" } as CSSProperties}>
      <div className="bz-mini-head">
        {square.kind === "city" ? <small>{square.group_name}</small> : <span aria-hidden="true">{ICONS[square.name]}</span>}
        <strong>{square.name}</strong>
      </div>
      <div className="bz-mini-row"><span>Price</span><b>{rupees(square.price ?? 0)}</b></div>
      {square.kind === "city" && <div className="bz-mini-row"><span>Rent</span><b>{rupees(square.rents?.[0] ?? 0)}</b></div>}
      {square.kind === "transport" && <div className="bz-mini-row"><span>Rent</span><b>{rupees(view.rules.transport_rents[0] ?? 0)}+</b></div>}
      {square.kind === "utility" && <div className="bz-mini-row"><span>Rent</span><b>{view.rules.utility_multipliers[0]}× dice</b></div>}
    </div>
  );
}

function CenterCard({ view, me, freshCard, delay }: { view: BusinessView; me: BizPlayer | undefined; freshCard: boolean; delay: number }) {
  const style = { "--delay": `${delay}ms` } as CSSProperties;
  if (view.result) {
    return (
      <div className="bz-card bz-result" style={style}>
        <Icon name="trophy" size={26} />
        <strong>{view.result.winners.map((w) => nameOf(view, w)).join(" & ") || "Game over"}</strong>
        <span>{view.result.reason}</span>
      </div>
    );
  }
  if (view.debt) {
    const mine = view.debt.debtor === view.you;
    return (
      <div className="bz-card bz-debt" style={style}>
        <span className="bz-card-kicker">Debt</span>
        <strong>{nameOf(view, view.debt.debtor)} {mine ? "owe" : "owes"} {rupees(view.debt.amount)}</strong>
        <span>{view.debt.what ? `${view.debt.what} · ` : ""}to {nameOrBank(view, view.debt.creditor)}</span>
        {mine && view.debt.short > 0 && <span className="bz-card-note">Raise {rupees(view.debt.short)} more by selling or mortgaging</span>}
      </div>
    );
  }
  if (freshCard && view.card) {
    return (
      <div key={view.card.seq} className={`bz-flip ${view.card.deck}`} style={style}>
        <div className="bz-flip-inner">
          <div className="bz-flip-back"><span>{view.card.deck === "chance" ? "?" : "🪙"}</span>{view.card.title}</div>
          <div className="bz-flip-front">
            <span className="bz-card-kicker">{view.card.title}</span>
            <p>{view.card.text}</p>
            <small>Drawn by {nameOf(view, view.card.player)}</small>
          </div>
        </div>
      </div>
    );
  }
  if (view.offer) {
    const square = view.board[view.offer.square];
    if (square) {
      return (
        <div className="bz-card bz-offer" style={style}>
          <span className="bz-card-kicker">{view.current === view.you ? "For sale" : `${nameOf(view, view.current)} may buy`}</span>
          <MiniDeed view={view} square={square} />
        </div>
      );
    }
  }
  if (me && me.in_jail && view.current === view.you && view.phase === "roll") {
    return (
      <div className="bz-card bz-jail-card" style={style}>
        <span className="bz-card-kicker">In Jail · attempt {me.jail_attempts + 1}/3</span>
        <strong>Pay {rupees(view.rules.jail_fine)} or roll for doubles</strong>
        {me.jail_attempts === 2 && <span className="bz-card-note">Last try: if it fails you pay the fine and move.</span>}
      </div>
    );
  }
  const current = view.players.find((p) => p.id === view.current);
  const dice = view.dice;
  return (
    <div className="bz-card bz-idle" style={style}>
      <span className="bz-card-kicker">{current ? `${nameOf(view, current.id)} ${current.id === view.you ? "are" : "is"} on` : ""}</span>
      <strong>{current ? view.board[current.position]?.name : ""}</strong>
      {dice && <span>Last roll {dice[0]} + {dice[1]} = {dice[0] + dice[1]}{dice[0] === dice[1] ? " · double!" : ""}</span>}
    </div>
  );
}

// ---------------------------------------------------------------- property card modal

function PropertyModal({ view, index, run, busy, onClose }: { view: BusinessView; index: number; run: Act; busy: boolean; onClose: () => void }) {
  const square = view.board[index];
  if (!square) return null;
  const owner = view.owners[index] ?? null;
  const houses = view.houses[index] ?? 0;
  const mortgaged = !!view.mortgaged[index];
  const groupOwned = !!square.group && view.board.filter((s) => s.group === square.group).every((s) => view.owners[s.index] === owner) && !!owner;
  const transportCount = owner ? view.board.filter((s) => s.kind === "transport" && view.owners[s.index] === owner).length : 0;
  const utilityCount = owner ? view.board.filter((s) => s.kind === "utility" && view.owners[s.index] === owner).length : 0;
  const rows: { label: string; value: string; on: boolean }[] = [];
  if (square.kind === "city" && square.rents) {
    rows.push({ label: "Rent", value: rupees(square.rents[0] ?? 0), on: !!owner && houses === 0 && !groupOwned });
    rows.push({ label: "With the whole group", value: rupees((square.rents[0] ?? 0) * 2), on: houses === 0 && groupOwned });
    for (let h = 1; h <= HOTEL; h++) rows.push({ label: `With ${ordinalHouses(h).toLowerCase()}`, value: rupees(square.rents[h] ?? 0), on: houses === h });
  } else if (square.kind === "transport") {
    view.rules.transport_rents.forEach((r, i) => rows.push({ label: `${i + 1} transport${i ? "s" : ""} owned`, value: rupees(r), on: transportCount === i + 1 }));
  } else if (square.kind === "utility") {
    view.rules.utility_multipliers.forEach((m, i) => rows.push({ label: i ? "Both utilities owned" : "One utility owned", value: `${m} × dice`, on: utilityCount === i + 1 }));
  }
  const can = (list: number[]) => list.includes(index);
  const cost = square.house_cost ?? 0;
  const go = (type: string) => { void run({ type, square: index }); };
  return (
    <Modal onClose={onClose} labelledBy="bz-deed-title">
      <div className={`bz-deed bz-deed-${square.kind}`} style={{ "--band": square.color ?? "#334155" } as CSSProperties}>
        <div className="bz-deed-head">
          <small>{square.kind === "city" ? `${square.group_name} group` : square.kind === "transport" ? "Transport" : "Utility"}</small>
          <h2 id="bz-deed-title">{square.kind !== "city" && <span aria-hidden="true">{ICONS[square.name]} </span>}{square.name}</h2>
        </div>
        <table className="bz-rents">
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className={r.on && !mortgaged ? "on" : ""}><td>{r.label}</td><td>{r.value}</td></tr>
            ))}
          </tbody>
        </table>
        <dl className="bz-facts">
          <div><dt>Price</dt><dd>{rupees(square.price ?? 0)}</dd></div>
          {square.kind === "city" && <div><dt>House / hotel</dt><dd>{rupees(cost)} each</dd></div>}
          <div><dt>Mortgage value</dt><dd>{rupees(square.mortgage ?? 0)}</dd></div>
          <div><dt>Unmortgage</dt><dd>{rupees(square.unmortgage ?? 0)}</dd></div>
        </dl>
        <div className="bz-deed-owner">
          {owner ? (
            <>
              <span className="bz-swatch" style={{ "--c": seatColor(view, owner) } as CSSProperties} />
              Owned by <b>{nameOf(view, owner)}</b>
              {houses > 0 && <span className="pill ok">{ordinalHouses(houses)}</span>}
              {mortgaged && <span className="pill warn">Mortgaged</span>}
            </>
          ) : <span className="muted">Owned by the bank</span>}
        </div>
      </div>
      <div className="modal-actions">
        {can(view.can_build) && <button className="success" disabled={busy} onClick={() => go("build")}>Build · {rupees(cost)}</button>}
        {can(view.can_sell) && <button className="secondary" disabled={busy} onClick={() => go("sell")}>Sell · +{rupees(cost / 2)}</button>}
        {can(view.can_mortgage) && <button className="secondary" disabled={busy} onClick={() => go("mortgage")}>Mortgage · +{rupees(square.mortgage ?? 0)}</button>}
        {can(view.can_unmortgage) && <button disabled={busy} onClick={() => go("unmortgage")}>Unmortgage · {rupees(square.unmortgage ?? 0)}</button>}
        <button className="ghost" onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- trading

function PropertyChecklist({ view, squares, picked, toggle }: { view: BusinessView; squares: Square[]; picked: Set<number>; toggle: (i: number) => void }) {
  if (squares.length === 0) return <p className="muted bz-empty">No tradable properties</p>;
  return (
    <ul className="bz-checklist">
      {squares.map((s) => (
        <li key={s.index}>
          <label>
            <input type="checkbox" checked={picked.has(s.index)} onChange={() => toggle(s.index)} />
            <span className="bz-dot" style={{ background: s.color ?? "#64748b" }} />
            <span className="grow">{s.name}</span>
            {view.mortgaged[s.index] && <span className="badge badge-warn">M</span>}
          </label>
        </li>
      ))}
    </ul>
  );
}

function TradeModal({ view, run, busy, onClose }: { view: BusinessView; run: Act; busy: boolean; onClose: () => void }) {
  const others = view.players.filter((p) => p.id !== view.you && !p.bankrupt);
  const me = view.players.find((p) => p.id === view.you);
  const [to, setTo] = useState(others[0]?.id ?? "");
  const [give, setGive] = useState<Set<number>>(new Set());
  const [get, setGet] = useState<Set<number>>(new Set());
  const [giveCash, setGiveCash] = useState("");
  const [getCash, setGetCash] = useState("");
  const partner = others.find((p) => p.id === to);
  const toggle = (set: Set<number>, update: (s: Set<number>) => void) => (i: number) => {
    const next = new Set(set);
    if (next.has(i)) next.delete(i); else next.add(i);
    update(next);
  };
  const cashOf = (text: string) => Math.max(0, Math.floor(Number(text) || 0));
  const gc = cashOf(giveCash), tc = cashOf(getCash);
  const empty = give.size === 0 && get.size === 0 && gc === 0 && tc === 0;
  const tooMuch = gc > (me?.cash ?? 0) || tc > (partner?.cash ?? 0);
  const send = async () => {
    const ok = await run({ type: "propose_trade", to, give: { cash: gc, squares: [...give] }, get: { cash: tc, squares: [...get] } });
    if (ok) onClose();
  };
  return (
    <Modal onClose={onClose} wide labelledBy="bz-trade-title">
      <h2 id="bz-trade-title">Propose a trade</h2>
      <div className="bz-partners" role="radiogroup" aria-label="Trade with">
        {others.map((p) => (
          <button key={p.id} type="button" role="radio" aria-checked={p.id === to}
            className={`secondary small${p.id === to ? " active" : ""}`}
            onClick={() => { setTo(p.id); setGet(new Set()); }}>
            <span className="bz-swatch" style={{ "--c": seatColor(view, p.id) } as CSSProperties} />
            {nameOf(view, p.id)}
          </button>
        ))}
      </div>
      <div className="bz-trade-cols">
        <section>
          <h3>You give</h3>
          <PropertyChecklist view={view} squares={tradable(view, view.you)} picked={give} toggle={toggle(give, setGive)} />
          <label className="field"><span>Cash (you have {rupees(me?.cash ?? 0)})</span>
            <input type="number" min={0} step={50} inputMode="numeric" placeholder="₹0" value={giveCash} onChange={(e) => setGiveCash(e.target.value)} />
          </label>
        </section>
        <section>
          <h3>You get</h3>
          <PropertyChecklist view={view} squares={to ? tradable(view, to) : []} picked={get} toggle={toggle(get, setGet)} />
          <label className="field"><span>Cash ({partner ? `${nameOf(view, partner.id)} has ${rupees(partner.cash)}` : ""})</span>
            <input type="number" min={0} step={50} inputMode="numeric" placeholder="₹0" value={getCash} onChange={(e) => setGetCash(e.target.value)} />
          </label>
        </section>
      </div>
      <p className="muted small-print">Properties in a colour group with buildings cannot be traded. Mortgaged properties change hands still mortgaged.</p>
      <div className="modal-actions">
        <button className="secondary" onClick={onClose}>Cancel</button>
        <button disabled={busy || empty || tooMuch || !to} onClick={() => void send()}>Send offer</button>
      </div>
    </Modal>
  );
}

function TradeCard({ view, trade, run, busy }: { view: BusinessView; trade: Trade; run: Act; busy: boolean }) {
  const incoming = trade.to === view.you;
  const outgoing = trade.from === view.you;
  return (
    <div className={`bz-trade-card${incoming ? " incoming" : ""}`}>
      <div className="bz-trade-title"><Icon name="handshake" size={18} />
        {incoming ? `${nameOf(view, trade.from)} offers you a trade` : outgoing ? `Offer sent to ${nameOf(view, trade.to)}` : `${nameOf(view, trade.from)} offered ${nameOf(view, trade.to)} a trade`}
      </div>
      <div className="bz-trade-lines">
        <div><span>{incoming ? "You get" : `${nameOf(view, trade.from)} ${outgoing ? "give" : "gives"}`}</span><b>{describeSide(view, trade.give)}</b></div>
        <div><span>{incoming ? "You give" : `${nameOf(view, trade.to)} gives`}</span><b>{describeSide(view, trade.get)}</b></div>
      </div>
      {incoming && (
        <div className="row">
          <button className="success small grow-btn" disabled={busy} onClick={() => void run({ type: "accept_trade" })}>Accept</button>
          <button className="danger small grow-btn" disabled={busy} onClick={() => void run({ type: "decline_trade" })}>Decline</button>
        </div>
      )}
      {outgoing && <button className="ghost small" disabled={busy} onClick={() => void run({ type: "cancel_trade" })}>Cancel offer</button>}
    </div>
  );
}

// ---------------------------------------------------------------- players

interface Floater { id: number; delta: number }

function PlayerRow({ view, player, floaters }: { view: BusinessView; player: BizPlayer; floaters: Floater[] }) {
  const cash = useCountUp(player.cash);
  const turn = player.id === view.current && !view.result;
  const winner = view.result?.winners.includes(player.id);
  return (
    <li className={`player-row bz-player${turn ? " is-turn" : ""}${player.bankrupt ? " is-out" : ""}`}
      data-player={player.id} data-cash={player.cash} style={{ "--c": seatColor(view, player.id) } as CSSProperties}>
      <span className="bz-avatar">
        <Avatar name={view.names[player.id] ?? "?"} size={36} ring={turn} />
        <span className="bz-seat-dot" />
      </span>
      <div className="grow">
        <div>
          {nameOf(view, player.id)}
          {player.in_jail && <span className="badge badge-warn bz-badge">Jail</span>}
          {player.bankrupt && <span className="badge badge-danger bz-badge">{player.left ? "Left" : "Bankrupt"}</span>}
        </div>
        <div className="sub">
          <span className="bz-cash">{rupees(cash)}</span> · {player.properties} {player.properties === 1 ? "property" : "properties"}
        </div>
      </div>
      <span className="bz-floaters" aria-hidden="true">
        {floaters.map((f) => (
          <span key={f.id} className={`bz-floater ${f.delta > 0 ? "up" : "down"}`}>{f.delta > 0 ? "+" : ""}{rupees(f.delta)}</span>
        ))}
      </span>
      {winner ? <Icon name="trophy" className="bz-win-icon" /> : turn && <span className="turn-chip">Turn</span>}
    </li>
  );
}

function useCashFloaters(players: BizPlayer[], delay: number): Record<string, Floater[]> {
  const [floaters, setFloaters] = useState<Record<string, Floater[]>>({});
  const previous = useRef<Record<string, number>>(Object.fromEntries(players.map((p) => [p.id, p.cash])));
  const nextId = useRef(1);
  const key = players.map((p) => `${p.id}:${p.cash}`).join("|");
  useEffect(() => {
    const changes: [string, number][] = [];
    for (const p of players) {
      const before = previous.current[p.id];
      if (before !== undefined && before !== p.cash) changes.push([p.id, p.cash - before]);
      previous.current[p.id] = p.cash;
    }
    if (changes.length === 0) return;
    const timers: number[] = [];
    timers.push(window.setTimeout(() => {
      const added = changes.map(([id, delta]) => [id, { id: nextId.current++, delta }] as const);
      setFloaters((all) => {
        const next = { ...all };
        for (const [id, f] of added) next[id] = [...(next[id] ?? []), f];
        return next;
      });
      timers.push(window.setTimeout(() => {
        const ids = new Set(added.map(([, f]) => f.id));
        setFloaters((all) => Object.fromEntries(Object.entries(all).map(([id, list]) => [id, list.filter((f) => !ids.has(f.id))])));
      }, 1800));
    }, delay));
    return () => timers.forEach((t) => window.clearTimeout(t));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return floaters;
}

function MyProperties({ view, onOpen }: { view: BusinessView; onOpen: (i: number) => void }) {
  const mine = view.board.filter((s) => isProperty(s) && view.owners[s.index] === view.you);
  if (mine.length === 0) return <p className="muted bz-empty">You don't own any property yet.</p>;
  const groups = groupsOf(view.board);
  const sections: { key: string; label: string; color: string; squares: Square[] }[] = [];
  for (const [key, squares] of groups) {
    const owned = squares.filter((s) => view.owners[s.index] === view.you);
    if (owned.length) sections.push({ key, label: `${squares[0]?.group_name} ${owned.length}/${squares.length}`, color: squares[0]?.color ?? "#64748b", squares: owned });
  }
  for (const kind of ["transport", "utility"] as const) {
    const owned = mine.filter((s) => s.kind === kind);
    const all = view.board.filter((s) => s.kind === kind).length;
    if (owned.length) sections.push({ key: kind, label: `${kind === "transport" ? "Transport" : "Utilities"} ${owned.length}/${all}`, color: "#475569", squares: owned });
  }
  return (
    <div className="bz-mine">
      {sections.map((sec) => (
        <div key={sec.key} className="bz-mine-group" style={{ "--band": sec.color } as CSSProperties}>
          <span className="bz-mine-label">{sec.label}</span>
          <div className="bz-mine-chips">
            {sec.squares.map((s) => {
              const h = view.houses[s.index] ?? 0;
              const legal = [view.can_build, view.can_sell, view.can_mortgage, view.can_unmortgage].some((l) => l.includes(s.index));
              return (
                <button key={s.index} type="button" className={`bz-chip${view.mortgaged[s.index] ? " mortgaged" : ""}${legal ? " legal" : ""}`} onClick={() => onOpen(s.index)}>
                  <span className="grow">{s.name}</span>
                  {h > 0 && <span className="bz-chip-b">{h === HOTEL ? "🏨" : `🏠${h}`}</span>}
                  {view.mortgaged[s.index] && <span className="bz-chip-m">M</span>}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      {view.can_build.length > 0 && <p className="bz-hint"><Icon name="sparkle" size={14} /> You can build — tap a highlighted city.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- the game

export function BusinessGame({ view, act }: GameProps<BusinessView>) {
  const { confirm } = useFeedback();
  const me = view.players.find((p) => p.id === view.you);
  const over = !!view.result;
  const can = (a: string) => view.actions.includes(a);
  const myTurn = !over && !!view.you && view.current === view.you;
  useTurnAlert(myTurn && can("roll"));

  const [busy, setBusy] = useState(false);
  const [openSquare, setOpenSquare] = useState<number | null>(null);
  const [trading, setTrading] = useState(false);
  const run: Act = async (action) => {
    if (busy) return false;
    setBusy(true);
    try {
      await act(action);
      return true;
    } catch {
      return false;
    } finally {
      setBusy(false);
    }
  };

  // Tokens wait for the dice; a walk then hops square by square.
  const placement = view.players.map((p) => `${p.position}${p.in_jail ? "j" : ""}`).join(",");
  const lagged = useLagged(placement, view.roll_seq, DIE_MS);
  const shownPlaces = lagged.split(",");
  const walkSteps = view.moves.filter((m) => m.walk).reduce((n, m) => n + ((m.to - m.from + 36) % 36), 0);
  const landDelay = view.moves.length ? DIE_MS + walkSteps * HOP_MS : 0;

  useOnChange(view.roll_seq, () => play("dice"));
  useOnChange(view.card?.seq, (before) => { if (view.card && before !== undefined) window.setTimeout(() => play("card"), landDelay); });
  useOnChange(view.owners.join(","), () => play("pop"));
  useOnChange(view.trade?.id ?? 0, () => { if (view.trade && view.trade.to === view.you) play("notify"); });

  // A drawn card stays on the board until the next roll.
  const [freshCard, setFreshCard] = useState(false);
  const cardSeq = view.card?.seq ?? 0;
  const seen = useRef({ card: cardSeq, roll: view.roll_seq });
  useEffect(() => {
    const cardChanged = cardSeq !== seen.current.card;
    const rollChanged = view.roll_seq !== seen.current.roll;
    seen.current = { card: cardSeq, roll: view.roll_seq };
    if (cardChanged) setFreshCard(true);
    else if (rollChanged) setFreshCard(false);
  }, [cardSeq, view.roll_seq]);

  const [boardRef, boardWidth] = useWidth<HTMLDivElement>();
  const dieSize = Math.round(Math.max(24, Math.min(54, boardWidth * 0.072)));
  const floaters = useCashFloaters(view.players, landDelay);

  const lastMove = view.moves[view.moves.length - 1];
  const hotSquare = lastMove ? lastMove.to : null;
  const active = view.players.filter((p) => !p.bankrupt);
  const offsets = (() => {
    const map = new Map<string, [number, number]>();
    const bySquare = new Map<string, string[]>();
    for (const p of active) {
      const place = shownPlaces[view.players.indexOf(p)] ?? `${p.position}`;
      bySquare.set(place, [...(bySquare.get(place) ?? []), p.id]);
    }
    for (const ids of bySquare.values()) {
      ids.forEach((id, i) => map.set(id, ids.length < 2 ? [0, 0] : CROWD[i % CROWD.length]!));
    }
    return map;
  })();

  const bankrupt = async () => {
    const ok = await confirm({
      title: "Declare bankruptcy?",
      body: view.debt ? `You owe ${rupees(view.debt.amount)} to ${nameOrBank(view, view.debt.creditor)}. Everything you own goes to them and you are out of the game.` : "You will be out of the game.",
      confirmLabel: "Declare bankruptcy",
      danger: true,
    });
    if (ok) await run({ type: "declare_bankruptcy" });
  };

  const status = statusText(view, me);
  const offerSquare = view.offer ? view.board[view.offer.square] : undefined;

  return (
    <div className="game business game-layout">
      <div className="bz-main">
        <div className="bz-frame">
          <div className="bz-board" ref={boardRef} style={{ "--delay": `${landDelay}ms` } as CSSProperties}>
            {view.board.map((s) => (
              <Tile key={s.index} view={view} square={s} hot={s.index === hotSquare} onOpen={setOpenSquare} />
            ))}
            <div className="bz-center">
              <svg className="bz-mandala" viewBox="-50 -50 100 100" aria-hidden="true">
                {Array.from({ length: 16 }, (_, i) => (
                  <ellipse key={i} cx="0" cy="-26" rx="7" ry="20" transform={`rotate(${i * 22.5})`} />
                ))}
                <circle r="44" /><circle r="12" /><circle r="47" className="thin" />
              </svg>
              <div className="bz-brand">
                <span className="bz-word">BUSINESS</span>
                <span className="bz-tag">Trade · Build · Prosper</span>
              </div>
              <div className="bz-dice">
                <Die value={view.dice?.[0] ?? null} rollKey={view.roll_seq} size={dieSize} />
                <Die value={view.dice?.[1] ?? null} rollKey={view.roll_seq} size={dieSize} />
              </div>
              <CenterCard view={view} me={me} freshCard={freshCard} delay={landDelay} />
              {view.ends_in_ms != null && !over && <TimeLeft ms={view.ends_in_ms} running />}
            </div>
            <div className="bz-token-layer">
              {active.map((p) => {
                const place = shownPlaces[view.players.indexOf(p)] ?? `${p.position}`;
                return (
                  <Token key={p.id} view={view} player={p.id} target={parseInt(place, 10)} jailed={place.endsWith("j")}
                    offset={offsets.get(p.id) ?? [0, 0]} isTurn={p.id === view.current && !over} />
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <aside className="side-panel bz-side">
        <p className={`game-status${myTurn ? " mine" : ""}${over ? " over" : ""}`}>
          <Icon name={over ? "trophy" : myTurn ? "sparkle" : "clock"} />
          {status}
        </p>

        {view.trade && <TradeCard view={view} trade={view.trade} run={run} busy={busy} />}

        {me && !me.bankrupt && !over && (
          <div className="bz-actions">
            {view.debt && view.debt.debtor === view.you ? (
              <>
                <button className="large block success" disabled={busy || !can("pay_debt")} onClick={() => void run({ type: "pay_debt" })}>
                  Pay debt
                </button>
                {can("declare_bankruptcy") && (
                  <button className="block danger" disabled={busy} onClick={() => void bankrupt()}>Declare bankruptcy</button>
                )}
                {view.debt.short > 0 && <p className="bz-hint">Raise {rupees(view.debt.short)}: open your properties below to sell or mortgage.</p>}
              </>
            ) : view.offer && myTurn ? (
              <div className="bz-buy-row">
                <button className="large success" disabled={busy || !can("buy")} onClick={() => void run({ type: "buy" })}>Buy</button>
                <button className="large secondary" disabled={busy || !can("decline")} onClick={() => void run({ type: "decline" })}>Decline</button>
                <span className="bz-buy-note">{offerSquare?.name} · {rupees(view.offer.price)}{!view.offer.affordable && " · not enough cash"}</span>
              </div>
            ) : can("end_turn") ? (
              <button className="large block" disabled={busy} onClick={() => void run({ type: "end_turn" })}>End turn</button>
            ) : (
              <button className="large block" disabled={busy || !can("roll")} onClick={() => void run({ type: "roll" })}>
                Roll dice
              </button>
            )}
            {can("pay_fine") && (
              <button className="block warm" disabled={busy} onClick={() => void run({ type: "pay_fine" })}>Pay fine</button>
            )}
            {can("propose_trade") && (
              <button className="block secondary" disabled={busy} onClick={() => setTrading(true)}>
                <Icon name="handshake" size={16} /> Propose trade
              </button>
            )}
          </div>
        )}

        <h3>Players</h3>
        <ul className="player-list">
          {view.players.map((p) => <PlayerRow key={p.id} view={view} player={p} floaters={floaters[p.id] ?? []} />)}
        </ul>

        {me && (
          <>
            <h3>My properties</h3>
            <MyProperties view={view} onOpen={setOpenSquare} />
          </>
        )}
        <GameLog view={view} />
      </aside>

      {openSquare !== null && (
        <PropertyModal view={view} index={openSquare} run={run} busy={busy} onClose={() => setOpenSquare(null)} />
      )}
      {trading && can("propose_trade") && <TradeModal view={view} run={run} busy={busy} onClose={() => setTrading(false)} />}
    </div>
  );
}
