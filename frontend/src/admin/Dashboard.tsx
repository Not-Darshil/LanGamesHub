import { useState, type FormEvent } from "react";
import { api, describeError } from "../api";
import { statusLabel } from "../labels";
import type { AdminPlayer, AdminRoom, AdminState, GameInfo } from "../types";

/** Runs an admin call and surfaces failures in a shared error banner. */
function useAction() {
  const [error, setError] = useState<string | null>(null);
  const run = async (method: string, path: string, body?: unknown) => {
    setError(null);
    try {
      await api(method, path, body);
    } catch (err) {
      setError(describeError(err));
    }
  };
  return { error, run, clear: () => setError(null) };
}

export function Dashboard({ state }: { state: AdminState }) {
  const action = useAction();
  return (
    <>
      {action.error && (
        <p className="error banner-error" onClick={action.clear}>
          {action.error} <span className="muted">(click to dismiss)</span>
        </p>
      )}
      <PendingQueue pending={state.pending} run={action.run} />
      <Players players={state.players} run={action.run} />
      <Rooms rooms={state.rooms} games={state.games} run={action.run} />
      <HostPlayer run={action.run} />
      <History state={state} />
    </>
  );
}

type Run = (method: string, path: string, body?: unknown) => Promise<void>;

function PendingQueue({ pending, run }: { pending: AdminPlayer[]; run: Run }) {
  return (
    <section className="panel">
      <h2>
        Access requests {pending.length > 0 && <span className="count">{pending.length}</span>}
      </h2>
      {pending.length === 0 ? (
        <p className="muted">No one is waiting.</p>
      ) : (
        <table>
          <thead>
            <tr><th>Request</th><th>IP address</th><th>Browser</th><th>Requested</th><th /></tr>
          </thead>
          <tbody>
            {pending.map((p) => (
              <tr key={p.id}>
                <td>#{p.id}{p.prior_rejections ? <span className="warn"> · {p.prior_rejections} earlier rejection(s) from this IP</span> : null}</td>
                <td><code>{p.ip_address}</code></td>
                <td className="ua">{p.user_agent}</td>
                <td>{new Date(p.created_at).toLocaleTimeString()}</td>
                <td className="actions">
                  <button onClick={() => run("POST", `/api/admin/players/${p.id}/approve`)}>Approve</button>
                  <button className="danger" onClick={() => run("POST", `/api/admin/players/${p.id}/reject`)}>Reject</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Players({ players, run }: { players: AdminPlayer[]; run: Run }) {
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const active = players.filter((p) => p.status === "APPROVED");
  const ended = players.filter((p) => p.status !== "APPROVED");

  const rename = async (event: FormEvent, id: number) => {
    event.preventDefault();
    await run("PUT", `/api/admin/players/${id}/nickname`, { nickname: draft });
    setEditing(null);
  };

  return (
    <section className="panel">
      <h2>Players</h2>
      {active.length === 0 ? (
        <p className="muted">No approved players yet.</p>
      ) : (
        <table>
          <thead>
            <tr><th>Nickname</th><th>IP address</th><th>Connection</th><th>Room</th><th>Screen</th><th /></tr>
          </thead>
          <tbody>
            {active.map((p) => (
              <tr key={p.id}>
                <td>
                  {editing === p.id ? (
                    <form className="row" onSubmit={(e) => rename(e, p.id)}>
                      <input autoFocus maxLength={20} value={draft} onChange={(e) => setDraft(e.target.value)} />
                      <button className="small">Save</button>
                      <button type="button" className="secondary small" onClick={() => setEditing(null)}>Cancel</button>
                    </form>
                  ) : (
                    <>
                      {p.nickname ?? <span className="muted">(choosing…)</span>}
                      {p.is_host && <span className="badge">host</span>}{" "}
                      <button className="link" onClick={() => { setEditing(p.id); setDraft(p.nickname ?? ""); }}>
                        rename
                      </button>
                    </>
                  )}
                </td>
                <td><code>{p.ip_address}</code></td>
                <td><span className={`dot ${p.online ? "dot-on" : "dot-off"}`} />{p.online ? "online" : "offline"}</td>
                <td>{p.room ? `${p.room.name} (${statusLabel(p.room.status)})` : <span className="muted">lobby</span>}</td>
                <td>
                  {p.screen === "HIDDEN" ? (
                    <>
                      <span className="badge badge-warn">hidden</span>{" "}
                      <button className="small" onClick={() => run("PUT", `/api/admin/players/${p.id}/screen`, { visibility: "VISIBLE" })}>
                        Restore Screen
                      </button>
                    </>
                  ) : (
                    <button className="small secondary" onClick={() => run("PUT", `/api/admin/players/${p.id}/screen`, { visibility: "HIDDEN" })}>
                      Hide Screen
                    </button>
                  )}
                </td>
                <td className="actions">
                  <button className="secondary small" disabled={!p.online}
                    onClick={() => run("POST", `/api/admin/players/${p.id}/disconnect`)}>Disconnect</button>
                  <button className="danger small" onClick={() => {
                    if (window.confirm(`Revoke ${p.nickname ?? "this player"}'s access? They will be removed from any room.`))
                      void run("POST", `/api/admin/players/${p.id}/revoke`);
                  }}>Revoke</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {ended.length > 0 && (
        <details>
          <summary className="muted">Rejected / revoked ({ended.length})</summary>
          <ul className="plain">
            {ended.map((p) => (
              <li key={p.id}>#{p.id} {p.nickname ?? ""} <code>{p.ip_address}</code> — {p.status.toLowerCase()}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function Rooms({ rooms, games, run }: { rooms: AdminRoom[]; games: GameInfo[]; run: Run }) {
  return (
    <section className="panel">
      <h2>Rooms</h2>
      <CreateRoom games={games} run={run} />
      {rooms.length === 0 ? (
        <p className="muted">No rooms.</p>
      ) : (
        <div className="admin-rooms">
          {rooms.map((r) => <RoomCard key={r.id} room={r} run={run} />)}
        </div>
      )}
    </section>
  );
}

function CreateRoom({ games, run }: { games: GameInfo[]; run: Run }) {
  const [gameType, setGameType] = useState("");
  const [name, setName] = useState("");
  const [maxPlayers, setMaxPlayers] = useState<number | null>(null);
  const game = games.find((g) => g.game_type === gameType) ?? games[0];
  if (!game) return <p className="muted">No games are available.</p>;
  const limit = maxPlayers !== null && maxPlayers >= game.min_players && maxPlayers <= game.max_players
    ? maxPlayers : game.max_players;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await run("POST", "/api/admin/rooms", { game_type: game.game_type, name: name || game.name, max_players: limit });
    setName("");
  };

  return (
    <form className="row create-room" onSubmit={submit}>
      <select value={game.game_type} onChange={(e) => { setGameType(e.target.value); setMaxPlayers(null); }}>
        {games.map((g) => <option key={g.game_type} value={g.game_type}>{g.name}</option>)}
      </select>
      <input placeholder="Room name" maxLength={40} value={name} onChange={(e) => setName(e.target.value)} />
      <label className="row">
        Player limit
        <select value={limit} onChange={(e) => setMaxPlayers(Number(e.target.value))}>
          {Array.from({ length: game.max_players - game.min_players + 1 }, (_, i) => game.min_players + i)
            .map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
      <button>Create room</button>
    </form>
  );
}

function RoomCard({ room, run }: { room: AdminRoom; run: Run }) {
  const base = `/api/admin/rooms/${room.id}`;
  const preStart = ["CREATED", "WAITING_FOR_PLAYERS", "READY_TO_START"].includes(room.status);
  const offline = room.members.filter((m) => !m.online);
  return (
    <article className={`room-card status-${room.status.toLowerCase()}`}>
      <header className="room-card-head">
        <div>
          <h3>{room.name}</h3>
          <p className="muted">{room.game_name} · created by {room.creator}</p>
        </div>
        <span className="badge">{statusLabel(room.status)}</span>
      </header>
      <p>
        {room.members.length}/{room.max_players} players (min {room.min_players})
        {room.is_locked && preStart && " · locked"}
      </p>
      <ul className="members">
        {room.members.map((m) => (
          <li key={m.session_id}>
            <span className={`dot ${m.online ? "dot-on" : "dot-off"}`} />
            {m.nickname}{m.is_host && <span className="badge">host</span>}
            {preStart && <span className="muted"> · {m.is_ready ? "ready" : "not ready"}</span>}
          </li>
        ))}
      </ul>
      {room.status === "IN_PROGRESS" && room.awaiting.length > 0 && (
        <p className="muted">Waiting on: {room.awaiting.join(", ")}</p>
      )}
      {room.result && (
        <p>
          <strong>{room.result.outcome === "WIN" ? `Winner: ${room.result.winners.join(", ")}` : room.result.outcome.toLowerCase()}</strong>
          {room.result.reason && <span className="muted"> — {room.result.reason}</span>}
        </p>
      )}
      {room.status === "READY_TO_START" && offline.length > 0 && (
        <p className="warn">Offline: {offline.map((m) => m.nickname).join(", ")}</p>
      )}
      <div className="row wrap">
        {room.status === "CREATED" && <button onClick={() => run("POST", `${base}/approve`)}>Approve room</button>}
        {preStart && room.status !== "CREATED" && (
          <button
            disabled={room.status !== "READY_TO_START"}
            title={room.status !== "READY_TO_START" ? "All required players must join and be ready" : ""}
            onClick={() => {
              if (window.confirm(`Start ${room.name} with ${room.members.map((m) => m.nickname).join(", ")}?`))
                void run("POST", `${base}/start`);
            }}
          >
            Start game
          </button>
        )}
        {preStart && (room.is_locked
          ? <button className="secondary" onClick={() => run("POST", `${base}/unlock`)}>Unlock</button>
          : <button className="secondary" onClick={() => run("POST", `${base}/lock`)}>Lock</button>)}
        {room.status === "IN_PROGRESS" && (
          <button className="secondary" onClick={() => {
            if (window.confirm("End this game now? It will be recorded as ended by the host.")) void run("POST", `${base}/finish`);
          }}>Finish game</button>
        )}
        {preStart && <button className="secondary" onClick={() => run("POST", `${base}/cancel`)}>Cancel</button>}
        <button className="danger" onClick={() => {
          if (window.confirm(`Remove room ${room.name}?`)) void run("DELETE", base);
        }}>Remove</button>
      </div>
    </article>
  );
}

function HostPlayer({ run }: { run: Run }) {
  const [nickname, setNickname] = useState("Host");
  return (
    <section className="panel">
      <h2>Play as the host</h2>
      <p className="muted">
        Opens the player view in a new tab with your own player identity (separate from this
        admin login). Join rooms there like any guest; this dashboard stays available here.
      </p>
      <form className="row" onSubmit={async (e) => {
        e.preventDefault();
        await run("POST", "/api/admin/host-player", { nickname });
        window.open("/", "_blank");
      }}>
        <input maxLength={20} value={nickname} onChange={(e) => setNickname(e.target.value)} />
        <button>Open player view</button>
      </form>
    </section>
  );
}

function History({ state }: { state: AdminState }) {
  if (state.history.length === 0) return null;
  return (
    <section className="panel">
      <h2>Recent matches</h2>
      <table>
        <thead><tr><th>Room</th><th>Game</th><th>Players</th><th>Result</th><th>Finished</th></tr></thead>
        <tbody>
          {state.history.map((h) => (
            <tr key={h.id}>
              <td>{h.room_name}</td>
              <td>{state.games.find((g) => g.game_type === h.game_type)?.name ?? h.game_type}</td>
              <td>{h.participants.join(", ")}</td>
              <td>{h.outcome === "WIN" ? `Won by ${h.winners.join(", ")}` : h.outcome.toLowerCase()}{h.reason ? ` (${h.reason})` : ""}</td>
              <td>{new Date(h.finished_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
