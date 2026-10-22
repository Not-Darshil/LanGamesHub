import { useEffect, useRef, useState } from "react";
import { play } from "./sound";

/** Plays a chime when it becomes your turn, and flashes the tab title while hidden. */
export function useTurnAlert(myTurn: boolean, message = "Your turn!"): void {
  const previous = useRef(myTurn);
  useEffect(() => {
    const was = previous.current;
    previous.current = myTurn;
    if (!myTurn || was) return;
    play("turn");
    if (!document.hidden) return;
    const original = document.title;
    let on = false;
    const timer = window.setInterval(() => {
      on = !on;
      document.title = on ? `● ${message}` : original;
    }, 1000);
    const stop = () => {
      if (document.hidden) return;
      window.clearInterval(timer);
      document.title = original;
      document.removeEventListener("visibilitychange", stop);
    };
    document.addEventListener("visibilitychange", stop);
    return () => {
      window.clearInterval(timer);
      document.title = original;
      document.removeEventListener("visibilitychange", stop);
    };
  }, [myTurn, message]);
}

/**
 * Animates through intermediate values on the way to `target` (e.g. a token hopping
 * square by square). `path(from, to)` returns the in-between values to show, ending
 * with `to`; return `[to]` to jump straight there.
 */
export function useStepped<T>(target: T, path: (from: T, to: T) => T[], stepMs = 140,
  equal: (a: T, b: T) => boolean = Object.is): T {
  const [shown, setShown] = useState(target);
  const shownRef = useRef(target);
  const pathRef = useRef(path);
  pathRef.current = path;

  useEffect(() => {
    if (equal(shownRef.current, target)) return;
    const steps = pathRef.current(shownRef.current, target);
    if (steps.length === 0) steps.push(target);
    let i = 0;
    const advance = () => {
      const next = steps[i++]!;
      shownRef.current = next;
      setShown(next);
    };
    advance();
    if (i >= steps.length) return;
    const timer = window.setInterval(() => {
      advance();
      if (i >= steps.length) window.clearInterval(timer);
    }, stepMs);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, stepMs]);

  return shown;
}

/** Re-renders on an interval while `active` (for countdowns). Returns performance.now(). */
export function useNow(active: boolean, intervalMs = 100): number {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(performance.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [active, intervalMs]);
  return active ? now : performance.now();
}

/** True once per change of `key` for `ms`: handy for one-shot CSS animations. */
export function useFlash(key: unknown, ms = 700): boolean {
  const [on, setOn] = useState(false);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    setOn(true);
    const timer = window.setTimeout(() => setOn(false), ms);
    return () => window.clearTimeout(timer);
  }, [key, ms]);
  return on;
}
