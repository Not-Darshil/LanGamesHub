import type { Standing } from "../types";
import { Avatar } from "./Avatar";

const MEDALS = ["🥇", "🥈", "🥉"];

export function placeLabel(place: number): string {
  return `#${place}`;
}

export function PlaceBadge({ place, size }: { place: number; size?: "small" }) {
  return (
    <span className={`place-badge place-${Math.min(place, 4)}${size ? ` ${size}` : ""}`} title={`Place ${place}`}>
      {place <= 3 ? <span aria-hidden="true">{MEDALS[place - 1]}</span> : null}#{place}
    </span>
  );
}

/** Final placings, best first. `me` (a nickname or player id) is highlighted. */
export function StandingsList({ standings, me, compact }: { standings: Standing[]; me?: string | null; compact?: boolean }) {
  return (
    <ol className={`standings${compact ? " compact" : ""}`}>
      {standings.map((row, i) => (
        <li key={row.id} className={`place-${Math.min(row.place, 4)}${me && (me === row.id || me === row.nickname) ? " me" : ""}`}
          style={{ animationDelay: `${i * 70}ms` }}>
          <PlaceBadge place={row.place} />
          {!compact && <Avatar name={row.nickname} size={30} />}
          <span className="standing-name">{row.nickname}</span>
          {row.detail && <span className="standing-detail">{row.detail}</span>}
        </li>
      ))}
    </ol>
  );
}
