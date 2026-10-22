import { useCallback, useEffect, useRef } from "react";
import { api, describeError } from "../api";
import { gameComponent } from "../games";
import "../games/all";
import { statusLabel, statusTone } from "../labels";
import type { GameViewBase, Member, RoomDetail, SessionInfo } from "../types";
import { Avatar } from "../ui/Avatar";
import { RoomChat } from "../ui/Chat";
import { fireConfetti } from "../ui/confetti";
import { useFeedback } from "../ui/Feedback";
import { GameIcon } from "../ui/games";
import { Icon } from "../ui/Icon";
import { play } from "../ui/sound";
import { PlaceBadge, StandingsList } from "../ui/Standings";

export function RoomView({
  room,
  game,
  me,
}: {
  room: RoomDetail;
  game: (GameViewBase & Record<string, unknown>) | null;
  me: SessionInfo;
}) {
  const { toast, confirm } = useFeedback();
  const mine = room.members.find((m) => m.session_id === me.id);
  const preStart = ["CREATED", "WAITING_FOR_PLAYERS", "READY_TO_START"].includes(room.status);
  const finished = room.status === "COMPLETED" || room.status === "CANCELLED";

  const call = async (path: string, body?: unknown) => {
    try {
      await api("POST", `/api/rooms/${room.id}/${path}`, body);
    } catch (err) {
      toast(describeError(err), "error");
    }
  };

  const act = useCallback(
    async (action: Record<string, unknown>) => {
      try {
        await api("POST", `/api/rooms/${room.id}/actions`, { action });
      } catch (err) {
        toast(describeError(err), "error");
        throw err;
      }
    },
    [room.id, toast],
  );

  const leave = async () => {
    if (room.status === "IN_PROGRESS") {
      const ok = await confirm({
        title: "Leave this game?", body: "Leaving forfeits the match. The other players will be told you left.",
        confirmLabel: "Leave and forfeit", danger: true,
      });
      if (!ok) return;
    }
    void call("leave");
  };

  // Celebrate (or commiserate) when a result arrives while watching, not on reload.
  const won = room.result?.outcome === "WIN" && !!me.nickname && room.result.winners.includes(me.nickname);
  const myPlace = room.result?.standings?.find((r) => r.id === String(me.id))?.place ?? null;
  const resultKey = room.result ? `${room.id}:${room.result.outcome}:${room.result.reason}` : null;
  const seenResult = useRef(resultKey);
  useEffect(() => {
    if (resultKey === seenResult.current) return;
    seenResult.current = resultKey;
    if (!resultKey || !room.result || room.result.outcome === "CANCELLED") return;
    if (won) {
      fireConfetti();
      play("win");
    } else if (room.result.outcome === "WIN") play("lose");
    else play("notify");
  }, [resultKey, room.result, won]);

  const Game = gameComponent(room.game_type);

  return (
    <section>
      <div className="room-header">
        <div className="room-title">
          <GameIcon gameType={room.game_type} size="large" />
          <div style={{ minWidth: 0 }}>
            <h2>{room.name}</h2>
            <div className="room-sub">
              <span className="pill">{room.game_name}</span>
              <span className={`pill ${statusTone(room.status)}`}>{statusLabel(room.status)}</span>
              {room.options_label && <span className="pill"><Icon name="clock" size={13} />{room.options_label}</span>}
              {room.is_locked && preStart && <span className="pill"><Icon name="lock" size={13} />locked by host</span>}
            </div>
          </div>
        </div>
        <div className="row">
          {!preStart && (
            <div className="seats" aria-label="Players">
              {room.members.map((m) => (
                <Avatar key={m.session_id} name={m.nickname} size={30} online={m.online}
                  ring={room.awaiting.includes(m.nickname)} title={`${m.nickname}${m.online ? "" : " (offline)"}`} />
              ))}
            </div>
          )}
          <button className={finished ? "" : "secondary"} onClick={() => void leave()}>
            <Icon name={finished ? "arrow-left" : "door"} size={16} />
            {finished ? "Back to lobby" : "Leave"}
          </button>
        </div>
      </div>

      {room.result && (
        <div className={`result${won ? "" : room.result.outcome === "WIN" ? " lost" : " neutral"}`}>
          <span className="result-icon" aria-hidden="true">
            {won ? "🏆" : room.result.outcome === "DRAW" ? "🤝" : room.result.outcome === "WIN" ? "🏁" : "⏹️"}
          </span>
          <div>
            {room.result.outcome === "WIN" && <strong>Winner: {room.result.winners.join(", ")}</strong>}
            {room.result.outcome === "DRAW" && <strong>Draw</strong>}
            {room.result.outcome === "ABORTED" && <strong>Game ended by the host</strong>}
            {room.result.outcome === "CANCELLED" && <strong>Game cancelled</strong>}
            {room.result.reason && <span className="muted"> — {room.result.reason}</span>}
          </div>
          <span className="spacer" />
          {won && <span className="pill ok">You won!</span>}
          {!won && myPlace && (room.result.standings?.length ?? 0) > 2 && <PlaceBadge place={myPlace} />}
          {(room.result.standings?.length ?? 0) > 2 && (
            <div className="result-standings"><StandingsList standings={room.result.standings!} me={String(me.id)} /></div>
          )}
        </div>
      )}
      {room.status === "CANCELLED" && !room.result && (
        <p className="notice">This room was cancelled{room.status_reason ? `: ${room.status_reason}` : ""}.</p>
      )}

      {preStart && <WaitingRoom room={room} me={me} mine={mine} onReady={(ready) => call("ready", { ready })} />}

      {game &&
        (Game ? (
          <div data-game-version={game.version}>
            <Game view={game} room={room} act={act} />
          </div>
        ) : (
          <p className="error">This game cannot be displayed.</p>
        ))}
      <RoomChat room={room} meId={me.id} />
    </section>
  );
}

function WaitingRoom({ room, me, mine, onReady }: {
  room: RoomDetail; me: SessionInfo; mine: Member | undefined; onReady: (ready: boolean) => void;
}) {
  const open = Math.max(0, room.max_players - room.members.length);
  const readyCount = room.members.filter((m) => m.is_ready).length;
  const message = room.status === "CREATED"
    ? "The host has to approve this room first."
    : room.status === "READY_TO_START"
      ? "Everyone is ready. The host will start the game."
      : `Waiting for players (${room.members.length}/${room.max_players}, minimum ${room.min_players}). Everyone must be ready.`;
  return (
    <div className="waiting-room">
      <div className="seat-grid">
        {room.members.map((m, i) => (
          <div key={m.session_id} className={`seat${m.is_ready ? " ready" : ""}${m.session_id === me.id ? " me" : ""}`} style={{ animationDelay: `${i * 60}ms` }}>
            <span className="seat-num">SEAT {m.seat + 1}</span>
            <Avatar name={m.nickname} size={56} online={m.online} />
            <strong>{m.nickname}{m.session_id === me.id && <span className="muted"> (you)</span>}</strong>
            <div className="row" style={{ gap: 4 }}>
              {m.is_host && <span className="badge" style={{ marginLeft: 0 }}>host</span>}
              <span className={`pill ${m.is_ready ? "ok" : ""}`}>{m.is_ready ? <><Icon name="check" size={13} />ready</> : "not ready"}</span>
            </div>
          </div>
        ))}
        {Array.from({ length: open }, (_, i) => (
          <div key={`open-${i}`} className="seat open" style={{ animationDelay: `${(room.members.length + i) * 60}ms` }}>
            <span className="seat-ring"><Icon name="user" /></span>
            <strong>Open seat</strong>
            <span className="small-print">Waiting for a player</span>
          </div>
        ))}
      </div>
      <div className="ready-cta">
        <h3 style={{ margin: 0 }}>Get ready</h3>
        <div className="progress-steps" aria-hidden="true">
          {room.members.map((m) => <span key={m.session_id} className={m.is_ready ? "done" : ""} />)}
        </div>
        <span className="small-print muted">{readyCount}/{room.members.length} ready{room.min_players ? ` · ${room.min_players}+ players needed` : ""}</span>
        <p className="status-line"><Icon name={room.status === "READY_TO_START" ? "sparkle" : "info"} size={18} /><span className="muted">{message}</span></p>
        {mine && (
          <button className={`large block ${mine.is_ready ? "secondary" : "success"}`} onClick={() => onReady(!mine.is_ready)}>
            {mine.is_ready ? "Not ready" : <><Icon name="check" />I'm ready</>}
          </button>
        )}
      </div>
    </div>
  );
}
