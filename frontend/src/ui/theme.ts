import { useSyncExternalStore } from "react";

/** Light/dark theme: follows the system until the user picks one, then remembers it. */
export type Theme = "light" | "dark";
const KEY = "lgh-theme";
const listeners = new Set<() => void>();

function stored(): Theme | null {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function system(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function apply(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#f3f4f9" : "#090c15");
  listeners.forEach((l) => l());
}

export function setTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(KEY, theme);
  } catch {
    /* preference only */
  }
  document.body.classList.add("theme-swap");
  window.setTimeout(() => document.body.classList.remove("theme-swap"), 400);
  apply(theme);
}

/** Call once before the first render so the page never flashes the wrong theme. */
export function initTheme(): void {
  apply(stored() ?? system());
  window.matchMedia?.("(prefers-color-scheme: light)").addEventListener?.("change", () => {
    if (!stored()) apply(system());
  });
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    currentTheme,
    currentTheme,
  );
}
