import { formatLog } from ".";
import type { GameViewBase } from "../types";

export function GameLog({ view }: { view: GameViewBase }) {
  const entries = view.log ?? [];
  if (entries.length === 0) return null;
  return (
    <details className="log-box" open>
      <summary>Game log</summary>
      <ol className="game-log" reversed>
        {[...entries].reverse().map((entry, i) => (
          <li key={entries.length - i}>{formatLog(view, entry)}</li>
        ))}
      </ol>
    </details>
  );
}
