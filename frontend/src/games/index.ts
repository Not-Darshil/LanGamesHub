import type { ComponentType } from "react";
import type { GameViewBase, RoomDetail } from "../types";

export interface GameProps<V extends GameViewBase = GameViewBase> {
  view: V;
  room: RoomDetail;
  /** Send an intent to the server; resolves once accepted, rejects with the reason. */
  act: (action: Record<string, unknown>) => Promise<void>;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyGame = ComponentType<GameProps<any>>;

const components: Record<string, AnyGame> = {};

export function registerGame(gameType: string, component: AnyGame): void {
  components[gameType] = component;
}

export function gameComponent(gameType: string): AnyGame | undefined {
  return components[gameType];
}

export function nameOf(view: GameViewBase, playerId: string | null | undefined): string {
  if (!playerId) return "";
  return playerId === view.you ? "You" : (view.names[playerId] ?? "Player");
}

/** Replace the server's {{playerId}} placeholders in log lines with nicknames. */
export function formatLog(view: GameViewBase, entry: string): string {
  return entry.replace(/\{\{([^}]+)\}\}/g, (_, id: string) => nameOf(view, id));
}
