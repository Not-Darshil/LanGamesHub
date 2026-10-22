import { useState, type FormEvent } from "react";
import { api, describeError } from "../api";
import { statusLabel } from "../labels";
import type { GameInfo, RoomSummary } from "../types";

export function Lobby({ lobby }: { lobby: { games: GameInfo[]; rooms: RoomSummary[] } }) {
  const [error, setError] = useState<string | null>(null);

  const join = async (roomId: number) => {
    setError(null);
    try {
      await api("POST", `/api/rooms/${roomId}/join`);
    } catch (err) {
      setError(describeError(err));
    }
  };

  return (
    <section>
      <h2>Lobby</h2>
      {error && <p className="error">{error}</p>}
      {lobby.rooms.length === 0 ? (
        <p className="muted">No rooms yet. Ask the host to open one, or propose one below.</p>
      ) : (
        <div className="room-grid">
          {lobby.rooms.map((room) => {
            const joinable =
              (room.status === "WAITING_FOR_PLAYERS" || room.status === "READY_TO_START") &&
              !room.is_locked &&
              room.players < room.max_players;
            return (
              <article key={room.id} className="room-card">
                <h3>{room.name}</h3>
                <p className="muted">{room.game_name}</p>
                <p>
                  {room.players}/{room.max_players} players · {statusLabel(room.status)}
                  {room.is_locked && " · locked"}
                </p>
                <button disabled={!joinable} onClick={() => join(room.id)}>
                  Join
                </button>
              </article>
            );
          })}
        </div>
      )}
      <ProposeRoom games={lobby.games} />
    </section>
  );
}

function ProposeRoom({ games }: { games: GameInfo[] }) {
  const [gameType, setGameType] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const game = games.find((g) => g.game_type === gameType) ?? games[0];

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!game) return;
    setError(null);
    try {
      await api("POST", "/api/rooms", { game_type: game.game_type, name: name || game.name });
      setName("");
    } catch (err) {
      setError(describeError(err));
    }
  };

  if (!game) return null;
  return (
    <details className="propose">
      <summary>Propose a room</summary>
      <p className="muted">The host must approve your room before others can join.</p>
      <form onSubmit={submit} className="row">
        <select value={game.game_type} onChange={(e) => setGameType(e.target.value)}>
          {games.map((g) => (
            <option key={g.game_type} value={g.game_type}>
              {g.name} ({g.min_players}–{g.max_players})
            </option>
          ))}
        </select>
        <input placeholder="Room name" maxLength={40} value={name}
          onChange={(e) => setName(e.target.value)} />
        <button>Propose</button>
      </form>
      {error && <p className="error">{error}</p>}
    </details>
  );
}
