import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type KeyboardEvent, type ReactNode } from "react";
import { nameOf, type GameProps } from "..";
import type { GameViewBase } from "../../types";
import { Avatar } from "../../ui/Avatar";
import { useFeedback } from "../../ui/Feedback";
import { useFlash, useNow, useTurnAlert } from "../../ui/hooks";
import { Icon } from "../../ui/Icon";
import { play } from "../../ui/sound";
import { seatColor } from "../colors";
import { GameLog } from "../GameLog";
import {
  MAX_EXTRA_CHARS, MAX_WRONG_CHARS, SEND_GAP_MS, correctPrefix, currentWord, formatClock, formatDuration,
  medal, ordinal, wordRanges, wpm,
} from "./helpers";
import "./typing.css";

interface Racer {
  id: string;
  pos: number;
  percent: number;
  finished: boolean;
  place: number | null;
  wpm: number;
  time_ms: number | null;
}

interface ResultRow { id: string; place: number; detail: string; wpm: number; finished: boolean }

interface TypingView extends GameViewBase {
  players: string[];
  length: string;
  length_label: string;
  passage: string;
  phase: "countdown" | "racing" | "over";
  starts_in_ms: number;
  ends_in_ms: number;
  elapsed_ms: number;
  limit_ms: number;
  racers: Racer[];
  me: Racer | null;
  result: { winners: string[]; draw: boolean; reason: string } | null;
  results: ResultRow[] | null;
}

const GO_SHOW_MS = 900;

export function TypingGame({ view, act }: GameProps<TypingView>) {
  const { toast } = useFeedback();
  const passage = view.passage ?? "";
  const racers = view.racers ?? [];
  const over = view.phase === "over";
  const me = view.me && view.you && view.me.id === view.you ? view.me : null;
  const isRacer = !!me;
  const serverFinished = !!me?.finished;

  // Times arrive relative to when the server built this view; count locally from here.
  const syncedAt = useMemo(() => performance.now(), [view]);
  const startLocal = syncedAt + (view.starts_in_ms ?? 0);
  const endLocal = syncedAt + (view.ends_in_ms ?? 0);
  const now = useNow(!over, 100);
  const startsIn = startLocal - now;
  // Once the server says the race is on, never fall back to the countdown locally.
  const phase = over ? "over" : view.phase === "racing" || startsIn <= 0 ? "racing" : "countdown";
  const elapsedMs = over ? view.elapsed_ms : phase === "racing" ? view.elapsed_ms + Math.max(0, now - syncedAt) : 0;
  const endsIn = over ? 0 : Math.max(0, endLocal - now);

  // Local typing state. After a reload, resume from the server's correct prefix.
  const [typed, setTyped] = useState(() => passage.slice(0, me?.pos ?? 0));
  const [keys, setKeys] = useState({ correct: 0, total: 0 });
  const [focused, setFocused] = useState(false);
  const [shake, setShake] = useState(0);
  const shaking = useFlash(shake, 400);
  const inputRef = useRef<HTMLInputElement>(null);
  const pos = correctPrefix(typed, passage);
  const canType = isRacer && phase === "racing" && !serverFinished;

  // ---- progress reports: one request in flight, at most one per SEND_GAP_MS ----
  const actRef = useRef(act);
  actRef.current = act;
  const latest = useRef(typed);
  const sent = useRef<string | null>(typed);
  const inFlight = useRef(false);
  const lastSentAt = useRef(0);
  const timer = useRef<number | undefined>(undefined);
  const failures = useRef(0);
  const live = useRef(true);
  const stopped = useRef(false);
  stopped.current = !canType;

  const flush = useCallback(() => {
    window.clearTimeout(timer.current);
    timer.current = undefined;
    if (!live.current || inFlight.current || stopped.current) return;
    const text = latest.current;
    if (text === sent.current) return;
    const wait = lastSentAt.current + SEND_GAP_MS - performance.now();
    if (wait > 0) {
      timer.current = window.setTimeout(flush, wait);
      return;
    }
    inFlight.current = true;
    lastSentAt.current = performance.now();
    actRef.current({ type: "progress", typed: text }).then(
      () => { sent.current = text; failures.current = 0; },
      () => {
        // RoomView already showed the reason. Do not hammer the server: retry a couple
        // of times (e.g. the final report arriving a hair too early), then wait for typing.
        sent.current = text;
        failures.current += 1;
        if (failures.current <= 2) {
          window.setTimeout(() => {
            if (latest.current === text) sent.current = null;
            flush();
          }, 1000);
        }
      },
    ).finally(() => {
      inFlight.current = false;
      if (live.current && latest.current !== sent.current) flush();
    });
  }, []);

  const schedule = useCallback((urgent: boolean) => {
    if (urgent) flush();
    else if (timer.current === undefined) timer.current = window.setTimeout(flush, SEND_GAP_MS);
  }, [flush]);

  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
      window.clearTimeout(timer.current);
    };
  }, []);

  // ---- countdown, GO and sounds ----
  const count = Math.ceil(startsIn / 1000);
  const sawCountdown = useRef(view.phase === "countdown");
  if (view.phase === "countdown") sawCountdown.current = true;
  const lastCount = useRef(count);
  useEffect(() => {
    if (count !== lastCount.current && count >= 1 && count <= 3 && !over) play("tick");
    lastCount.current = count;
  }, [count, over]);
  useTurnAlert(canType, "GO! Start typing");

  useEffect(() => {
    if (canType) inputRef.current?.focus({ preventScroll: true });
  }, [canType]);

  // Low-time ticks while you are still racing.
  const secondsLeft = Math.ceil(endsIn / 1000);
  const lastSecond = useRef(secondsLeft);
  useEffect(() => {
    if (canType && secondsLeft !== lastSecond.current && secondsLeft > 0 && secondsLeft <= 10) play("tick");
    lastSecond.current = secondsLeft;
  }, [secondsLeft, canType]);

  // A pop whenever somebody crosses the line.
  const finishedCount = racers.filter((r) => r.finished).length;
  const lastFinished = useRef(finishedCount);
  useEffect(() => {
    if (finishedCount > lastFinished.current) play("pop");
    lastFinished.current = finishedCount;
  }, [finishedCount]);

  // ---- input handling ----
  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (!canType) return;
    let next = event.target.value;
    const limit = Math.min(passage.length + MAX_EXTRA_CHARS, correctPrefix(next, passage) + MAX_WRONG_CHARS);
    if (next.length > limit) {
      next = next.slice(0, limit);
      setShake((s) => s + 1);
      play("error");
    }
    if (next.length > typed.length && next.startsWith(typed)) {
      let p = pos;
      let correct = 0;
      for (let i = typed.length; i < next.length; i++) {
        if (i === p && next[i] === passage[i]) { correct++; p++; }
      }
      const added = next.length - typed.length;
      setKeys((k) => ({ correct: k.correct + correct, total: k.total + added }));
    }
    if (next === typed) return;
    setTyped(next);
    latest.current = next;
    const nextPos = correctPrefix(next, passage);
    const wordDone = next.length > typed.length && nextPos === next.length && passage[nextPos - 1] === " ";
    schedule(wordDone || next === passage);
  };

  // Keep the caret at the end: no arrow keys, no clicking into the middle.
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"].includes(event.key)) {
      event.preventDefault();
    }
    if (event.key === "Enter") event.preventDefault();
  };
  const pinCaret = () => {
    const el = inputRef.current;
    if (el && (el.selectionStart !== el.value.length || el.selectionEnd !== el.value.length)) {
      el.setSelectionRange(el.value.length, el.value.length);
    }
  };

  // ---- passage rendering (memoized: only changes when typing changes) ----
  const ranges = useMemo(() => wordRanges(passage), [passage]);
  const showCaret = isRacer && !over && !serverFinished;
  const rendered = useMemo(() => {
    const caret = showCaret ? Math.min(typed.length, passage.length) : -1;
    const active = showCaret ? currentWord(ranges, pos) : -1;
    const ch = (i: number) => {
      const state = i < pos ? "ok" : i < typed.length ? "bad" : "todo";
      const c = passage[i]!;
      return (
        <span key={i} className={`ty-ch ${state}${c === " " ? " sp" : ""}${i === caret ? " caret" : ""}`}>{c}</span>
      );
    };
    const out: ReactNode[] = [];
    let i = 0;
    ranges.forEach(([start, end], w) => {
      while (i < start) out.push(ch(i++));
      const chars = [];
      for (; i < end; i++) chars.push(ch(i));
      out.push(<span key={`w${w}`} className={`ty-word${w === active ? " current" : ""}`}>{chars}</span>);
    });
    while (i < passage.length) out.push(ch(i++));
    if (caret === passage.length) out.push(<span key="end" className="ty-ch todo caret end">{"​"}</span>);
    return out;
  }, [passage, ranges, typed, pos, showCaret]);

  // ---- derived numbers ----
  const myWpm = serverFinished ? me!.wpm : wpm(pos, elapsedMs);
  const accuracy = keys.total ? Math.round((keys.correct / keys.total) * 100) : null;
  const errorsNow = typed.length > pos;
  const liveWpmOf = (r: Racer) => (r.finished ? r.wpm : wpm(r.id === me?.id && !over ? pos : r.pos, elapsedMs));
  const pctOf = (r: Racer) => (r.id === me?.id && !over ? Math.floor((pos * 100) / Math.max(1, passage.length)) : r.percent);

  const result = view.result;
  const winners = result?.winners ?? [];
  const status = result
    ? result.draw ? `Draw — ${result.reason}`
      : winners.includes(view.you) ? `You won — ${result.reason}`
      : `${winners.map((w) => nameOf(view, w)).join(" & ")} won — ${result.reason}`
    : phase === "countdown" ? `Get ready — starting in ${Math.max(1, count)}…`
    : serverFinished ? `You finished ${ordinal(me!.place ?? 1)} at ${me!.wpm} WPM — waiting for the others`
    : isRacer && typed === passage ? "Crossing the line…"
    : isRacer ? "GO! Type the passage"
    : "Race in progress";

  const timePct = over ? 0 : phase === "countdown" ? 100 : Math.min(100, (endsIn / Math.max(1, view.limit_ms)) * 100);
  const lowTime = phase === "racing" && endsIn < 15_000;
  const showGo = !over && sawCountdown.current && startsIn > -GO_SHOW_MS;
  const order = [...racers].sort((a, b) => view.players.indexOf(a.id) - view.players.indexOf(b.id));

  return (
    <div className="game typing game-layout">
      <div className="ty-main">
        <section className="ty-card ty-track-card" aria-label="Race track">
          <div className="ty-card-head">
            <h3><Icon name="flag" size={15} />Race</h3>
            <span className="pill">{view.length_label}</span>
          </div>
          <ol className="ty-lanes">
            {order.map((r) => {
              const pct = pctOf(r);
              const color = seatColor(view, r.id);
              return (
                <li key={r.id} className={`ty-lane${r.id === me?.id ? " me" : ""}${r.finished ? " done" : ""}`}
                  style={{ ["--seat" as string]: color }}>
                  <div className="ty-lane-head">
                    <span className="ty-seat-dot" />
                    <span className="ty-lane-name">{nameOf(view, r.id)}</span>
                    <span className="ty-lane-wpm">{liveWpmOf(r)} <small>WPM</small></span>
                    {r.finished && r.place ? (
                      <span className="ty-lane-place" title={`Finished ${ordinal(r.place)}`}>{medal(r.place)}</span>
                    ) : (
                      <span className="ty-lane-pct">{pct}%</span>
                    )}
                  </div>
                  <div className="ty-road">
                    <span className="ty-road-fill" style={{ width: `${pct}%` }} />
                    <span className="ty-finish-line" aria-hidden="true" />
                    <span className={`ty-car${phase === "racing" && !r.finished && pct > 0 ? " moving" : ""}`}
                      style={{ ["--p" as string]: pct }} aria-hidden="true">
                      <Car color={color} />
                    </span>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>

        <section className={`ty-card ty-type-card${canType ? " live" : ""}`} aria-label="Passage">
          <div className={`ty-time${lowTime ? " low" : ""}`} role="timer" aria-label="Time left">
            <Icon name="clock" size={14} />
            <span className="ty-time-label">{over ? "Race over" : phase === "countdown" ? formatClock(view.limit_ms) : formatClock(endsIn)}</span>
            <span className="ty-time-bar"><span style={{ width: `${timePct}%` }} /></span>
          </div>

          <div className={`ty-passage-box${errorsNow ? " has-error" : ""}${shaking ? " shake" : ""}`}
            onMouseDown={(e) => { if (canType && e.target !== inputRef.current) { e.preventDefault(); inputRef.current?.focus(); } }}>
            <p className="ty-passage" data-passage={passage} aria-hidden="true">{rendered}</p>
            <span className="ty-sr">{passage}</span>
            {isRacer && !over && (
              <input ref={inputRef} className="ty-input" type="text" aria-label="Type the passage here"
                value={typed} readOnly={!canType} maxLength={passage.length + MAX_EXTRA_CHARS}
                autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck={false} inputMode="text"
                onChange={onChange} onKeyDown={onKeyDown} onSelect={pinCaret} onClick={pinCaret}
                onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
                onPaste={(e) => { e.preventDefault(); toast("Pasting is disabled", "info"); }}
                onDrop={(e) => e.preventDefault()} onContextMenu={(e) => e.preventDefault()} />
            )}
            {canType && !focused && (
              <span className="ty-focus-hint"><Icon name="edit" size={14} />Click here and keep typing</span>
            )}
            {(phase === "countdown" || showGo) && (
              <div className={`ty-countdown${phase === "countdown" ? "" : " go"}`} aria-live="assertive">
                {phase === "countdown" ? (
                  count > 3 ? (
                    <><span className="ty-count small" key={`c${count}`}>{count}</span><span className="ty-count-sub">Get ready…</span></>
                  ) : (
                    <span className="ty-count" key={`c${count}`}>{count}</span>
                  )
                ) : (
                  <span className="ty-count go" key="go">GO!</span>
                )}
              </div>
            )}
          </div>

          {isRacer && !over && (
            <div className="ty-stats">
              <Stat label="WPM" value={phase === "countdown" ? "—" : String(myWpm)} accent />
              <Stat label="Accuracy" value={accuracy === null ? "—" : `${accuracy}%`} />
              <Stat label="Progress" value={`${Math.floor((pos * 100) / Math.max(1, passage.length))}%`} />
              <Stat label={serverFinished ? "Place" : "Chars"} value={serverFinished ? medal(me!.place ?? 1) : `${pos}/${passage.length}`} />
            </div>
          )}
        </section>

        {over && view.results && (
          <section className="ty-card ty-results" aria-label="Race results">
            <div className="ty-card-head"><h3><Icon name="trophy" size={15} />Race results</h3>
              {result && <span className="pill ok">{result.reason}</span>}</div>
            <ol className="ty-results-list">
              {view.results.map((row, i) => (
                <li key={row.id} className={`place-${Math.min(row.place, 4)}${row.id === view.you ? " me" : ""}`}
                  style={{ animationDelay: `${i * 80}ms`, ["--seat" as string]: seatColor(view, row.id) }}>
                  <span className="ty-medal">{medal(row.place)}</span>
                  <Avatar name={view.names[row.id] ?? "Player"} size={28} color={seatColor(view, row.id)} />
                  <span className="ty-result-name">{nameOf(view, row.id)}</span>
                  <span className="ty-result-wpm">{row.finished ? `${row.wpm} WPM` : row.detail}</span>
                </li>
              ))}
            </ol>
            {me && (
              <div className="ty-mine">
                <Stat label="Your speed" value={`${me.finished ? me.wpm : wpm(me.pos, view.elapsed_ms)} WPM`} accent />
                <Stat label="Accuracy" value={accuracy === null ? "—" : `${accuracy}%`} />
                <Stat label="Time" value={me.time_ms !== null ? formatDuration(me.time_ms) : `${me.percent}% done`} />
              </div>
            )}
          </section>
        )}
      </div>

      <aside className="side-panel">
        <p className={`game-status${canType ? " mine" : ""}${over ? " over" : ""}`}>{status}</p>
        <h3>Racers</h3>
        <ul className="player-list">
          {order.map((r) => (
            <li key={r.id} className={`player-row${r.finished ? "" : phase === "racing" ? " racing" : ""}`}>
              <Avatar name={view.names[r.id] ?? "Player"} size={32} color={seatColor(view, r.id)} />
              <div className="grow">
                <div>{nameOf(view, r.id)}</div>
                <div className="sub">
                  {r.finished && r.place ? `Finished ${ordinal(r.place)} · ${r.wpm} WPM` : `${pctOf(r)}% · ${liveWpmOf(r)} WPM`}
                </div>
              </div>
              {r.finished && r.place ? <span className="ty-side-medal">{medal(r.place)}</span> : null}
            </li>
          ))}
        </ul>
        <GameLog view={view} />
      </aside>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`ty-stat${accent ? " accent" : ""}`}>
      <span className="ty-stat-value">{value}</span>
      <span className="ty-stat-label">{label}</span>
    </div>
  );
}

/** A little side-view race car in the player's colour (inline SVG: no assets). */
function Car({ color }: { color: string }) {
  return (
    <svg viewBox="0 0 48 24" width="46" height="23">
      <path d="M3 17.5v-4.2c0-1.4 1-2.3 2.4-2.5l8.6-1.1 6.2-5.3c.8-.7 1.8-1 2.9-1h8.8c1.3 0 2.4.6 3.2 1.6l3.7 4.8 4.4.9c1.6.3 2.8 1.7 2.8 3.4v3.4c0 .9-.7 1.5-1.5 1.5H4.5c-.8 0-1.5-.6-1.5-1.5z"
        fill={color} stroke="rgb(0 0 0 / 35%)" strokeWidth="0.8" />
      <path d="M17.2 9.6 21.8 5.7c.4-.3.9-.5 1.4-.5h4.6v4.4z" fill="rgb(255 255 255 / 75%)" />
      <path d="M29.6 5.2h3c.7 0 1.3.3 1.7.8l2.8 3.6h-7.5z" fill="rgb(255 255 255 / 75%)" />
      <path d="M5 13.5h7" stroke="rgb(255 255 255 / 55%)" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="13" cy="18.5" r="4.2" fill="#111827" />
      <circle cx="13" cy="18.5" r="1.7" fill="#d1d5db" />
      <circle cx="37" cy="18.5" r="4.2" fill="#111827" />
      <circle cx="37" cy="18.5" r="1.7" fill="#d1d5db" />
    </svg>
  );
}
