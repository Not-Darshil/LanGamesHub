import { useState, type FormEvent } from "react";
import { api, describeError } from "../api";
import { statusLabel, statusTone } from "../labels";
import type { GameInfo, RoomSummary } from "../types";
import { useFeedback, Modal } from "../ui/Feedback";
import { GameIcon, gameMeta } from "../ui/games";
import { Icon } from "../ui/Icon";
import { Tabs } from "../ui/Tabs";
import { TimeControlPicker } from "../ui/TimeControlPicker";
import { MyMatches } from "./MyMatches";

export function Lobby({ lobby, nickname }: { lobby: { games: GameInfo[]; rooms: RoomSummary[] }; nickname: string }) {
  const { toast } = useFeedback();
  const [proposing, setProposing] = useState<GameInfo | null>(null);
  const [joining, setJoining] = useState<number | null>(null);
  const [tab, setTab] = useState<"play" | "history">("play");

  const join = async (roomId: number) => {
    setJoining(roomId);
    try {
      await api("POST", `/api/rooms/${roomId}/join`);
    } catch (err) {
      toast(describeError(err), "error");
    } finally {
      setJoining(null);
    }
  };

  const open = lobby.rooms.filter((r) => r.status !== "IN_PROGRESS");
  const live = lobby.rooms.filter((r) => r.status === "IN_PROGRESS");

  return (
    <section>
      <div className="hero">
        <div className="eyebrow">Welcome, {nickname}</div>
        <h1>Lobby</h1>
        <p>Jump into an open room, or pick a game below to propose a new one. The host starts every match.</p>
        <div className="hero-art" aria-hidden="true">
          <span style={{ background: gameMeta("uno").gradient }}>🃏</span>
          <span style={{ background: gameMeta("chess").gradient }}>♞{"︎"}</span>
          <span style={{ background: gameMeta("ludo").gradient }}>🎲</span>
        </div>
      </div>

      <div className="lobby-tabs">
        <Tabs label="Lobby sections" value={tab} onChange={setTab} tabs={[
          { key: "play", label: "Play" },
          { key: "history", label: "My matches" },
        ]} />
      </div>
      {tab === "history" ? <div className="tab-panel"><MyMatches refreshKey={lobby.rooms.length} /></div> : <div className="tab-panel">
      <div className="section-head">
        <div>
          <h2>Open rooms</h2>
          <p>{open.length === 0 ? "Nothing open right now." : `${open.length} room${open.length === 1 ? "" : "s"} you can join`}</p>
        </div>
      </div>
      {open.length === 0 ? (
        <div className="empty">
          <span className="empty-icon"><Icon name="gamepad" size={26} /></span>
          <strong>No rooms yet</strong>
          <span>Ask the host to open one, or propose one from the games below.</span>
        </div>
      ) : (
        <div className="room-grid stagger">
          {open.map((room, i) => (
            <LobbyRoom key={room.id} room={room} index={i} busy={joining === room.id} onJoin={() => join(room.id)} />
          ))}
        </div>
      )}

      {live.length > 0 && (
        <>
          <div className="section-head"><div><h2>Now playing</h2><p>Matches in progress on this network</p></div></div>
          <div className="room-grid stagger">
            {live.map((room, i) => <LobbyRoom key={room.id} room={room} index={i} busy={false} onJoin={() => {}} />)}
          </div>
        </>
      )}

      <div className="section-head">
        <div><h2>Pick a game</h2><p>Propose a room; the host approves it before others can join.</p></div>
      </div>
      <div className="game-tile-grid stagger">
        {lobby.games.map((g, i) => (
          <button key={g.game_type} type="button" className="game-tile" style={{ ["--tile" as string]: gameMeta(g.game_type).gradient, ["--i" as string]: i }}
            onClick={() => setProposing(g)}>
            <GameIcon gameType={g.game_type} />
            <strong>{g.name}</strong>
            <small>{gameMeta(g.game_type).tagline || g.description}</small>
            <span className="tile-foot"><Icon name="users" size={14} />{g.min_players === g.max_players ? g.min_players : `${g.min_players}–${g.max_players}`} players</span>
          </button>
        ))}
      </div>
      </div>}
      {proposing && <ProposeRoom game={proposing} onClose={() => setProposing(null)} />}
    </section>
  );
}

function LobbyRoom({ room, index, busy, onJoin }: { room: RoomSummary; index: number; busy: boolean; onJoin: () => void }) {
  const joinable =
    (room.status === "WAITING_FOR_PLAYERS" || room.status === "READY_TO_START") &&
    !room.is_locked &&
    room.players < room.max_players;
  const label = room.status === "IN_PROGRESS" ? "In progress" : room.is_locked ? "Locked" : room.players >= room.max_players ? "Full" : "Join";
  return (
    <article className={`room-card status-${room.status.toLowerCase()}`} style={{ ["--i" as string]: index }}>
      <div className="room-card-head">
        <div className="room-card-title">
          <GameIcon gameType={room.game_type} />
          <div>
            <h3>{room.name}</h3>
            <p className="muted">{room.game_name} · by {room.creator}</p>
          </div>
        </div>
      </div>
      <div className="room-meta">
        <span className={`pill ${statusTone(room.status)}`}>{statusLabel(room.status)}</span>
        {room.options_label && <span className="pill"><Icon name="clock" size={13} />{room.options_label}</span>}
        {room.is_locked && <span className="pill"><Icon name="lock" size={13} />locked</span>}
      </div>
      <div>
        <div className="row between small-print" style={{ marginBottom: 6 }}>
          <span className="muted">{room.players}/{room.max_players} players</span>
          {room.min_players && room.players < room.min_players && <span className="muted">needs {room.min_players - room.players} more</span>}
        </div>
        <div className="capacity"><span style={{ width: `${(room.players / room.max_players) * 100}%` }} /></div>
      </div>
      {room.status !== "IN_PROGRESS" && (
        <button className="block" disabled={!joinable || busy} onClick={onJoin}>
          {label === "Join" && <Icon name="play" size={14} />}{label}
        </button>
      )}
    </article>
  );
}

function ProposeRoom({ game, onClose }: { game: GameInfo; onClose: () => void }) {
  const { toast } = useFeedback();
  const [name, setName] = useState("");
  const [maxPlayers, setMaxPlayers] = useState(game.max_players);
  const [timeControl, setTimeControl] = useState<string | null>("10+0");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isChess = game.game_type === "chess";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("POST", "/api/rooms", {
        game_type: game.game_type, name: name || game.name, max_players: maxPlayers,
        ...(isChess && timeControl ? { options: { time_control: timeControl } } : {}),
      });
      toast("Room proposed. Waiting for the host to approve it.", "success");
      onClose();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal onClose={onClose} wide={isChess} labelledBy="propose-title">
      <div className="row" style={{ gap: 14, marginBottom: 14 }}>
        <GameIcon gameType={game.game_type} size="large" />
        <div>
          <h2 id="propose-title" style={{ margin: 0 }}>Propose a {game.name} room</h2>
          <p className="muted" style={{ margin: "2px 0 0" }}>The host must approve your room before others can join.</p>
        </div>
      </div>
      <form onSubmit={submit} className="stack">
        <label className="field">
          <span>Room name</span>
          <input autoFocus placeholder={game.name} maxLength={40} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        {game.min_players !== game.max_players && (
          <div className="field">
            <span>Players</span>
            <div className="segmented">
              {Array.from({ length: game.max_players - game.min_players + 1 }, (_, i) => game.min_players + i).map((n) => (
                <button key={n} type="button" className={maxPlayers === n ? "active" : ""} onClick={() => setMaxPlayers(n)}>{n}</button>
              ))}
            </div>
          </div>
        )}
        {isChess && (
          <div className="field">
            <span>Time control</span>
            <TimeControlPicker value={timeControl} onChange={setTimeControl} />
          </div>
        )}
        {error && <p className="error">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button disabled={busy}>Propose room</button>
        </div>
      </form>
    </Modal>
  );
}
