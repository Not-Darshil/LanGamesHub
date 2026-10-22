import { useSyncExternalStore } from "react";
import { isMuted, setMuted, subscribeMuted } from "./sound";

export function useMuted(): [boolean, (muted: boolean) => void] {
  const muted = useSyncExternalStore(subscribeMuted, isMuted, isMuted);
  return [muted, setMuted];
}
