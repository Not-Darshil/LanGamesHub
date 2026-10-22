import { formatLog } from ".";
import type { GameViewBase } from "../types";
import { Icon } from "../ui/Icon";

export function GameLog({ view, title = "Game log" }: { view: GameViewBase; title?: string }) {
  const entries = view.log ?? [];
  if (entries.length === 0) return null;
  return (
    <details className="log-box" open>
      <summary>
        <span>{title}</span>
        <Icon name="chevron-down" size={16} className="chev" />
      </summary>
      <ol className="game-log" reversed>
        {[...entries].reverse().map((entry, i) => (
          <li key={entries.length - i}>{formatLog(view, entry)}</li>
        ))}
      </ol>
    </details>
  );
}
