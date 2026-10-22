import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, describeError } from "../api";
import { statusLabel, statusTone } from "../labels";
import type { AdminPlayer, AdminRoom, AdminState, GameInfo } from "../types";
import { Avatar } from "../ui/Avatar";
import { useFeedback } from "../ui/Feedback";
import { GameIcon } from "../ui/games";
import { Icon, type IconName } from "../ui/Icon";
import { play } from "../ui/sound";
import { TimeControlPicker } from "../ui/TimeControlPicker";

type Run = (method: string, path: string, body?: unknown) => Promise<boolean>;

/** Runs an admin call; failures become an error toast. Resolves to success. */
function useRun(): Run {
  const { toast } = useFeedback();
  return async (method, path, body) => {
    try {
      await api(method, path, body);
      return true;
    } catch (err) {
      toast(describeError(err), "error");
      return false;
    }
  };
}

export function Dashboard({ state }: { state: AdminState }) {
  const run = useRun();

  // Chime when a new access request arrives.
  const pendingCount = state.pending.length;
  const previous = useRef(pendingCount);
  useEffect(() => {
    if (pendingCount > previous.current) play("notify");
    previous.current = pendingCount;
  }, [pendingCount]);

  const online = state.players.filter((p) => p.status === "APPROVED" && p.online).length;
  const live = state.rooms.filter((r) => r.status === "IN_PROGRESS").length;
  const ready = state.rooms.filter((r) => r.status === "READY_TO_START").length;

  return (
    <>
      <div className="stat-grid">
        <Stat icon="shield" label="Access requests" value={pendingCount} tone={pendingCount ? "warn" : ""} />
        <Stat icon="users" label="Players online" value={online} tone="ok" />
        <Stat icon="play" label="Ready to start" value={ready} tone={ready ? "ok" : ""} />
        <Stat icon="gamepad" label="Live games" value={live} tone="accent" />
      </div>
      <PendingQueue pending={state.pending} run={run} />
      <Rooms rooms={state.rooms} games={state.games} run={run} />
      <Players players={state.players} run={run} />
      <div className="dash-two">
        <HostPlayer run={run} />
        <History state={state} />
      </div>
    </>
  );
}

function Stat({ icon, label, value, tone }: { icon: IconName; label: string; value: number; tone: string }) {
  return (
    <div className={`stat ${tone}`}>
      <span className="stat-icon"><Icon name={icon} size={20} /></span>
      <div>
        <strong key={value}>{value}</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

function PendingQueue({ pending, run }: { pending: AdminPlayer[]; run: Run }) {
  return (
    <section className={`panel${pending.length ? " attention" : ""}`}>
      <div className="panel-head">
        <h2>
          Access requests {pending.length > 0 && <span className="count">{pending.length}</span>}
        </h2>
        {pending.length > 1 && (
          <button className="success small" onClick={async () => {
            for (const p of pending) await run("POST", `/api/admin/players/${p.id}/approve`);
          }}><Icon name="check" size={14} />Approve all</button>
        )}
      </div>
      {pending.length === 0 ? (
        <div className="empty">
          <span className="empty-icon"><Icon name="shield" size={24} /></span>
          <strong>No one is waiting</strong>
          <span>Guests who enter the room password appear here for approval.</span>
        </div>
      ) : (
        <table>
          <thead>
            <tr><th>Request</th><th>IP address</th><th>Browser</th><th>Requested</th><th /></tr>
          </thead>
          <tbody>
            {pending.map((p) => (
              <tr key={p.id} className="row-new">
                <td>
                  <strong>#{p.id}</strong>
                  {p.prior_rejections ? <div className="warn small-print">{p.prior_rejections} earlier rejection(s) from this IP</div> : null}
                </td>
                <td><code>{p.ip_address}</code></td>
                <td className="ua" title={p.user_agent}>{browserName(p.user_agent)}</td>
                <td className="muted">{new Date(p.created_at).toLocaleTimeString()}</td>
                <td className="actions">
                  <button className="success small" onClick={() => run("POST", `/api/admin/players/${p.id}/approve`)}>
                    <Icon name="check" size={14} />Approve
                  </button>
                  <button className="danger small" onClick={() => run("POST", `/api/admin/players/${p.id}/reject`)}>
                    <Icon name="x" size={14} />Reject
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function browserName(ua: string): string {
  const os = /Windows/.test(ua) ? "Windows" : /Mac OS X/.test(ua) ? "macOS" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Linux/.test(ua) ? "Linux" : "";
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser";
  return os ? `${browser} on ${os}` : ua || "Unknown";
}

function Players({ players, run }: { players: AdminPlayer[]; run: Run }) {
  const { confirm } = useFeedback();
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const active = players.filter((p) => p.status === "APPROVED");
  const ended = players.filter((p) => p.status !== "APPROVED");

  const rename = async (event: FormEvent, id: number) => {
    event.preventDefault();
    if (await run("PUT", `/api/admin/players/${id}/nickname`, { nickname: draft })) setEditing(null);
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Players <span className="pill">{active.length}</span></h2>
      </div>
      {active.length === 0 ? (
        <div className="empty">
          <span className="empty-icon"><Icon name="users" size={24} /></span>
          <strong>No approved players yet</strong>
        </div>
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
                      <input autoFocus maxLength={20} value={draft} onChange={(e) => setDraft(e.target.value)} style={{ width: 140 }} />
                      <button className="small">Save</button>
                      <button type="button" className="secondary small" onClick={() => setEditing(null)}>Cancel</button>
                    </form>
                  ) : (
                    <span className="row">
                      <Avatar name={p.nickname ?? "?"} size={30} online={p.online} />
                      <span>
                        {p.nickname ?? <span className="muted">(choosing…)</span>}
                        {p.is_host && <span className="badge">host</span>}{" "}
                        <button className="link" onClick={() => { setEditing(p.id); setDraft(p.nickname ?? ""); }}>
                          rename
                        </button>
                      </span>
                    </span>
                  )}
                </td>
                <td><code>{p.ip_address}</code></td>
                <td><span className={`pill ${p.online ? "ok" : ""}`}><span className={`dot ${p.online ? "dot-on" : "dot-off"}`} style={{ marginRight: 0 }} />{p.online ? "online" : "offline"}</span></td>
                <td>{p.room ? <span>{p.room.name} <span className="muted small-print">({statusLabel(p.room.status)})</span></span> : <span className="muted">lobby</span>}</td>
                <td>
                  {p.screen === "HIDDEN" ? (
                    <span className="row">
                      <span className="badge badge-warn">hidden</span>
                      <button className="small" onClick={() => run("PUT", `/api/admin/players/${p.id}/screen`, { visibility: "VISIBLE" })}>
                        <Icon name="eye" size={14} />Restore Screen
                      </button>
                    </span>
                  ) : (
                    <button className="small secondary" onClick={() => run("PUT", `/api/admin/players/${p.id}/screen`, { visibility: "HIDDEN" })}>
                      <Icon name="eye-off" size={14} />Hide Screen
                    </button>
                  )}
                </td>
                <td className="actions">
                  <button className="secondary small" disabled={!p.online}
                    onClick={() => run("POST", `/api/admin/players/${p.id}/disconnect`)}><Icon name="plug" size={14} />Disconnect</button>
                  <button className="danger small" onClick={async () => {
                    const ok = await confirm({
                      title: `Revoke ${p.nickname ?? "this player"}?`,
                      body: "They lose access immediately and are removed from any room. A game in progress counts as a forfeit.",
                      confirmLabel: "Revoke access", danger: true,
                    });
                    if (ok) void run("POST", `/api/admin/players/${p.id}/revoke`);
                  }}>Revoke</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {ended.length > 0 && (
        <details className="ended">
          <summary className="muted"><Icon name="chevron-down" size={14} /> Rejected / revoked ({ended.length})</summary>
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
  const active = rooms.filter((r) => r.status !== "COMPLETED" && r.status !== "CANCELLED");
  const done = rooms.filter((r) => r.status === "COMPLETED" || r.status === "CANCELLED");
  return (
    <section className="panel">
      <div className="panel-head"><h2>Rooms <span className="pill">{active.length}</span></h2></div>
      <CreateRoom games={games} run={run} />
      {rooms.length === 0 ? (
        <div className="empty">
          <span className="empty-icon"><Icon name="gamepad" size={24} /></span>
          <strong>No rooms</strong>
          <span>Create one above. Guests can also propose rooms for you to approve.</span>
        </div>
      ) : (
        <div className="admin-rooms stagger">
          {[...active, ...done].map((r, i) => <RoomCard key={r.id} room={r} run={run} index={i} />)}
        </div>
      )}
    </section>
  );
}

function CreateRoom({ games, run }: { games: GameInfo[]; run: Run }) {
  const [gameType, setGameType] = useState("");
  const [name, setName] = useState("");
  const [maxPlayers, setMaxPlayers] = useState<number | null>(null);
  const [timeControl, setTimeControl] = useState<string | null>(null);
  const game = games.find((g) => g.game_type === gameType) ?? games[0];
  if (!game) return <p className="muted">No games are available.</p>;
  const limit = maxPlayers !== null && maxPlayers >= game.min_players && maxPlayers <= game.max_players
    ? maxPlayers : game.max_players;
  const isChess = game.game_type === "chess";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const ok = await run("POST", "/api/admin/rooms", {
      game_type: game.game_type, name: name || game.name, max_players: limit,
      ...(isChess && timeControl ? { options: { time_control: timeControl } } : {}),
    });
    if (ok) setName("");
  };

  return (
    <form className="create-room" onSubmit={submit}>
      <div className="create-room-row">
        <GameIcon gameType={game.game_type} />
        <label className="field">
          <span>Game</span>
          <select value={game.game_type} onChange={(e) => { setGameType(e.target.value); setMaxPlayers(null); }}>
            {games.map((g) => <option key={g.game_type} value={g.game_type}>{g.name}</option>)}
          </select>
        </label>
        <label className="field grow">
          <span>Room name</span>
          <input placeholder="Room name" maxLength={40} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <span>Player limit</span>
          <select value={limit} onChange={(e) => setMaxPlayers(Number(e.target.value))}>
            {Array.from({ length: game.max_players - game.min_players + 1 }, (_, i) => game.min_players + i)
              .map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <button className="create-btn"><Icon name="plus" size={16} />Create room</button>
      </div>
      {isChess && (
        <div className="field" style={{ marginTop: 14 }}>
          <span>Time control</span>
          <TimeControlPicker value={timeControl} onChange={setTimeControl} />
        </div>
      )}
    </form>
  );
}

function RoomCard({ room, run, index }: { room: AdminRoom; run: Run; index: number }) {
  const { confirm } = useFeedback();
  const base = `/api/admin/rooms/${room.id}`;
  const preStart = ["CREATED", "WAITING_FOR_PLAYERS", "READY_TO_START"].includes(room.status);
  const finished = room.status === "COMPLETED" || room.status === "CANCELLED";
  const offline = room.members.filter((m) => !m.online);
  return (
    <article className={`room-card status-${room.status.toLowerCase()}${finished ? " finished" : ""}`} style={{ ["--i" as string]: index }}>
      <header className="room-card-head">
        <div className="room-card-title">
          <GameIcon gameType={room.game_type} />
          <div>
            <h3>{room.name}</h3>
            <p className="muted">{room.game_name} · by {room.creator}</p>
          </div>
        </div>
      </header>
      <div className="room-meta">
        <span className={`pill ${statusTone(room.status)}${room.status === "IN_PROGRESS" ? " live" : ""}`}>{statusLabel(room.status)}</span>
        {room.options_label && <span className="pill"><Icon name="clock" size={13} />{room.options_label}</span>}
        {room.is_locked && preStart && <span className="pill"><Icon name="lock" size={13} />locked</span>}
        <span className="pill"><Icon name="users" size={13} />{room.members.length}/{room.max_players} (min {room.min_players})</span>
      </div>
      {room.members.length > 0 && (
        <ul className="members">
          {room.members.map((m) => (
            <li key={m.session_id} className={room.awaiting.includes(m.nickname) ? "turn" : ""}>
              <Avatar name={m.nickname} size={24} online={m.online} />
              {m.nickname}{m.is_host && <span className="badge">host</span>}
              {preStart && <span className={m.is_ready ? "ok-text" : "muted"}>{m.is_ready ? "✓" : "·"}</span>}
            </li>
          ))}
        </ul>
      )}
      {room.status === "IN_PROGRESS" && room.awaiting.length > 0 && (
        <p className="muted small-print">Waiting on: {room.awaiting.join(", ")}</p>
      )}
      {room.result && (
        <p className="small-print">
          <strong>{room.result.outcome === "WIN" ? `🏆 Winner: ${room.result.winners.join(", ")}` : room.result.outcome.toLowerCase()}</strong>
          {room.result.reason && <span className="muted"> — {room.result.reason}</span>}
        </p>
      )}
      {room.status === "READY_TO_START" && offline.length > 0 && (
        <p className="warn small-print">Offline: {offline.map((m) => m.nickname).join(", ")}</p>
      )}
      <div className="row wrap card-actions">
        {room.status === "CREATED" && <button className="small" onClick={() => run("POST", `${base}/approve`)}><Icon name="check" size={14} />Approve room</button>}
        {preStart && room.status !== "CREATED" && (
          <button
            className={`small${room.status === "READY_TO_START" ? " success glow-ready" : ""}`}
            disabled={room.status !== "READY_TO_START"}
            title={room.status !== "READY_TO_START" ? "All required players must join and be ready" : ""}
            onClick={async () => {
              const ok = await confirm({
                title: `Start ${room.name}?`,
                body: <>Players: <strong>{room.members.map((m) => m.nickname).join(", ")}</strong>{room.options_label ? <> · {room.options_label}</> : null}</>,
                confirmLabel: "Start now",
              });
              if (ok) void run("POST", `${base}/start`);
            }}
          >
            <Icon name="play" size={14} />Start game
          </button>
        )}
        {preStart && (room.is_locked
          ? <button className="secondary small" onClick={() => run("POST", `${base}/unlock`)}><Icon name="unlock" size={14} />Unlock</button>
          : <button className="secondary small" onClick={() => run("POST", `${base}/lock`)}><Icon name="lock" size={14} />Lock</button>)}
        {room.status === "IN_PROGRESS" && (
          <button className="secondary small" onClick={async () => {
            const ok = await confirm({
              title: "End this game now?", body: "It will be recorded as ended by the host, with no winner.",
              confirmLabel: "End game", danger: true,
            });
            if (ok) void run("POST", `${base}/finish`);
          }}><Icon name="flag" size={14} />Finish game</button>
        )}
        {preStart && <button className="secondary small" onClick={() => run("POST", `${base}/cancel`)}>Cancel</button>}
        <button className="danger small icon-btn" aria-label="Remove" title="Remove room" onClick={async () => {
          const ok = await confirm({ title: `Remove ${room.name}?`, body: finished ? "The match history is kept." : "Anyone in it returns to the lobby.", confirmLabel: "Remove room", danger: true });
          if (ok) void run("DELETE", base);
        }}><Icon name="trash" size={14} /></button>
      </div>
    </article>
  );
}

function HostPlayer({ run }: { run: Run }) {
  const [nickname, setNickname] = useState("Host");
  return (
    <section className="panel">
      <div className="panel-head"><h2><Icon name="gamepad" />Play as the host</h2></div>
      <p className="muted small-print">
        Opens the player view in a new tab with your own player identity (separate from this
        admin login). Join rooms there like any guest; this dashboard stays available here.
      </p>
      <form className="row" style={{ marginTop: 12 }} onSubmit={async (e) => {
        e.preventDefault();
        if (await run("POST", "/api/admin/host-player", { nickname })) window.open("/", "_blank");
      }}>
        <input maxLength={20} value={nickname} onChange={(e) => setNickname(e.target.value)} style={{ flex: 1 }} />
        <button><Icon name="external" size={14} />Open player view</button>
      </form>
    </section>
  );
}

function History({ state }: { state: AdminState }) {
  return (
    <section className="panel">
      <div className="panel-head"><h2><Icon name="history" />Recent matches</h2></div>
      {state.history.length === 0 ? (
        <p className="muted small-print">Finished matches appear here.</p>
      ) : (
        <ul className="history">
          {state.history.map((h) => (
            <li key={h.id}>
              <GameIcon gameType={h.game_type} size="small" />
              <div className="grow">
                <div><strong>{h.room_name}</strong> <span className="muted small-print">{state.games.find((g) => g.game_type === h.game_type)?.name ?? h.game_type}</span></div>
                <div className="small-print muted">{h.participants.join(", ")}</div>
              </div>
              <div className="history-result">
                <span className={`pill ${h.outcome === "WIN" ? "ok" : h.outcome === "DRAW" ? "accent" : ""}`}>
                  {h.outcome === "WIN" ? `Won by ${h.winners.join(", ")}` : h.outcome.toLowerCase()}
                </span>
                <span className="small-print muted">{h.reason ? `${h.reason} · ` : ""}{new Date(h.finished_at).toLocaleString()}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
