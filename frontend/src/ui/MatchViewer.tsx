import { useEffect, useState } from "react";
import { api, describeError } from "../api";
import { gameComponent } from "../games";
import "../games/all";
import type { HistoryEntry, MatchDetail, RoomDetail } from "../types";
import { Modal } from "./Feedback";
import { GameIcon } from "./games";
import { Icon } from "./Icon";
import { PlaceBadge, StandingsList } from "./Standings";

export function formatWhen(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  return sameDay
    ? `Today, ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
    : date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function outcomeText(m: { outcome: string; winners: string[] }): string {
  if (m.outcome === "WIN") return `Won by ${m.winners.join(", ")}`;
  if (m.outcome === "DRAW") return "Draw";
  if (m.outcome === "ABORTED") return "Ended by the host";
  return "Cancelled";
}

function duration(m: MatchDetail): string | null {
  if (!m.started_at) return null;
  const minutes = Math.round((new Date(m.finished_at).getTime() - new Date(m.started_at).getTime()) / 60000);
  return minutes < 1 ? "under a minute" : `${minutes} min`;
}

/**
 * A finished match: result, placings and the final position, rendered with the game's
 * own component in a read-only (inert) wrapper. `url` is the detail endpoint.
 */
export function MatchViewer({ url, me, onClose }: { url: string; me?: string | null; onClose: () => void }) {
  const [match, setMatch] = useState<MatchDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api<MatchDetail>("GET", url).then((m) => live && setMatch(m), (e) => live && setError(describeError(e)));
    return () => { live = false; };
  }, [url]);

  const Game = match ? gameComponent(match.game_type) : undefined;
  const room: RoomDetail | null = match && {
    id: 0, name: match.room_name, game_type: match.game_type, game_name: match.game_name, status: "COMPLETED",
    players: match.participants?.length ?? 0, min_players: null, max_players: match.participants?.length ?? 0,
    is_locked: true, creator: "", members: [], status_reason: null, awaiting: [],
    result: { outcome: match.outcome as "WIN", winners: match.winners, reason: match.reason, standings: match.standings ?? [] },
  };

  return (
    <Modal onClose={onClose} wide labelledBy="match-title">
      <div className="match-viewer">
        <button type="button" className="ghost icon-btn small match-close" aria-label="Close" onClick={onClose}><Icon name="x" /></button>
        {error && <p className="error">{error}</p>}
        {!match && !error && <div className="spinner" />}
        {match && (
          <>
            <div className="row" style={{ gap: 14 }}>
              <GameIcon gameType={match.game_type} size="large" />
              <div style={{ minWidth: 0 }}>
                <h2 id="match-title" style={{ margin: 0 }}>{match.room_name}</h2>
                <div className="row wrap" style={{ marginTop: 6, gap: 6 }}>
                  <span className="pill">{match.game_name}</span>
                  <span className={`pill ${match.outcome === "WIN" ? "ok" : match.outcome === "DRAW" ? "accent" : ""}`}>{outcomeText(match)}</span>
                  <span className="pill"><Icon name="clock" size={13} />{formatWhen(match.finished_at)}{duration(match) ? ` · ${duration(match)}` : ""}</span>
                </div>
              </div>
            </div>
            {match.reason && <p className="muted small-print" style={{ marginTop: 10 }}>{match.reason}</p>}
            {(match.standings?.length ?? 0) > 0 && (
              <>
                <h3 className="viewer-heading">Final standings</h3>
                <StandingsList standings={match.standings} me={me ?? (match.game?.you || null)} />
              </>
            )}
            <h3 className="viewer-heading">Where it ended</h3>
            {match.game && Game && room ? (
              <div className="replay-frame">
                <span className="replay-tag"><Icon name="flag" size={13} />Final position</span>
                <div className="replay-inner" inert>
                  <Game view={match.game} room={room} act={() => Promise.reject(new Error("This match is over"))} />
                </div>
              </div>
            ) : (
              <div className="empty"><strong>No final position saved</strong><span>Matches played before this feature was added have no end screen.</span></div>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}

export function MatchRow({ match, index, onOpen, mine }: { match: HistoryEntry; index: number; onOpen: () => void; mine?: boolean }) {
  const standings = match.standings ?? []; // older servers do not send standings
  const top = standings.slice(0, 3);
  return (
    <button type="button" className="match-row" style={{ animationDelay: `${Math.min(index, 10) * 40}ms` }} onClick={onOpen}
      aria-label={`Open ${match.room_name}`}>
      <GameIcon gameType={match.game_type} size="small" />
      <div className="grow">
        <div className="match-title">{match.room_name} <span className="muted small-print">{match.game_name}</span></div>
        {top.length > 0 && standings.length > 2 ? (
          <div className="podium">{top.map((r) => <span key={r.id}><b>#{r.place}</b>{r.nickname}</span>)}</div>
        ) : (
          <div className="match-sub">{(match.participants ?? []).join(" vs ")}</div>
        )}
      </div>
      <div className="match-side">
        {mine && match.my_place && (match.outcome === "WIN" || match.outcome === "DRAW") ? <PlaceBadge place={match.my_place} /> : (
          <span className={`pill ${match.outcome === "WIN" ? "ok" : match.outcome === "DRAW" ? "accent" : ""}`}>{outcomeText(match)}</span>
        )}
        <span className="small-print muted">{formatWhen(match.finished_at)}</span>
      </div>
      <Icon name="chevron-down" className="chev-right" />
    </button>
  );
}
