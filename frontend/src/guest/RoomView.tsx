import { useCallback, useState } from "react";
import { api, describeError } from "../api";
import { gameComponent } from "../games";
import "../games/all";
import { statusLabel } from "../labels";
import type { GameViewBase, RoomDetail, SessionInfo } from "../types";

export function RoomView({
  room,
  game,
  me,
}: {
  room: RoomDetail;
  game: (GameViewBase & Record<string, unknown>) | null;
  me: SessionInfo;
}) {
  const [error, setError] = useState<string | null>(null);
  const mine = room.members.find((m) => m.session_id === me.id);
  const preStart = ["CREATED", "WAITING_FOR_PLAYERS", "READY_TO_START"].includes(room.status);
  const finished = room.status === "COMPLETED" || room.status === "CANCELLED";

  const call = async (path: string, body?: unknown) => {
    setError(null);
    try {
      await api("POST", `/api/rooms/${room.id}/${path}`, body);
    } catch (err) {
      setError(describeError(err));
    }
  };

  const act = useCallback(
    async (action: Record<string, unknown>) => {
      setError(null);
      try {
        await api("POST", `/api/rooms/${room.id}/actions`, { action });
      } catch (err) {
        setError(describeError(err));
        throw err;
      }
    },
    [room.id],
  );

  const Game = gameComponent(room.game_type);

  return (
    <section>
      <div className="room-header">
        <div>
          <h2>{room.name}</h2>
          <p className="muted">
            {room.game_name} · {statusLabel(room.status)}
            {room.is_locked && preStart && " · locked by host"}
          </p>
        </div>
        <div className="row">
          {preStart && mine && (
            <button onClick={() => call("ready", { ready: !mine.is_ready })}>
              {mine.is_ready ? "Not ready" : "I'm ready"}
            </button>
          )}
          <button
            className="secondary"
            onClick={() => {
              if (room.status !== "IN_PROGRESS" || window.confirm("Leaving forfeits the game. Leave?"))
                void call("leave");
            }}
          >
            {finished ? "Back to lobby" : "Leave"}
          </button>
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      <ul className="members">
        {room.members.map((m) => (
          <li key={m.session_id} className={room.awaiting.includes(m.nickname) ? "turn" : ""}>
            <span className={`dot ${m.online ? "dot-on" : "dot-off"}`} />
            {m.nickname}
            {m.session_id === me.id && " (you)"}
            {m.is_host && <span className="badge">host</span>}
            {preStart && <span className="muted"> {m.is_ready ? "· ready" : "· not ready"}</span>}
          </li>
        ))}
      </ul>

      {preStart && (
        <p className="muted">
          {room.status === "CREATED"
            ? "The host has to approve this room first."
            : room.status === "READY_TO_START"
              ? "Everyone is ready. The host will start the game."
              : `Waiting for players (${room.members.length}/${room.max_players}, minimum ${room.min_players}). Everyone must be ready.`}
        </p>
      )}

      {room.result && (
        <div className="result">
          {room.result.outcome === "WIN" && <strong>Winner: {room.result.winners.join(", ")}</strong>}
          {room.result.outcome === "DRAW" && <strong>Draw</strong>}
          {room.result.outcome === "ABORTED" && <strong>Game ended by the host</strong>}
          {room.result.outcome === "CANCELLED" && <strong>Game cancelled</strong>}
          {room.result.reason && <span className="muted"> — {room.result.reason}</span>}
        </div>
      )}
      {room.status === "CANCELLED" && !room.result && (
        <p className="notice">This room was cancelled{room.status_reason ? `: ${room.status_reason}` : ""}.</p>
      )}

      {game &&
        (Game ? (
          <div data-game-version={game.version}>
            <Game view={game} room={room} act={act} />
          </div>
        ) : (
          <p className="error">This game cannot be displayed.</p>
        ))}
    </section>
  );
}
