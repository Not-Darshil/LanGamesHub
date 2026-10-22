import { useSyncExternalStore } from "react";
import { isHostMuted, isMuted, setMuted, subscribeMuted } from "./sound";

/** The player's own sound preference. */
export function useMuted(): [boolean, (muted: boolean) => void] {
  const muted = useSyncExternalStore(subscribeMuted, isMuted, isMuted);
  return [muted, setMuted];
}

/** Whether the host has muted this browser. */
export function useHostMuted(): boolean {
  return useSyncExternalStore(subscribeMuted, isHostMuted, isHostMuted);
}
