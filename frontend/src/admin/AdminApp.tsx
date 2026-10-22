import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api, describeError } from "../api";
import type { AdminState } from "../types";
import { CLOSE_UNAUTHENTICATED, useSocket } from "../useSocket";
import { Dashboard } from "./Dashboard";

type Phase = "loading" | "login" | "ready";

export function AdminApp() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [username, setUsername] = useState<string | null>(null);
  const [state, setState] = useState<AdminState | null>(null);

  useEffect(() => {
    document.title = "LanGamesHub · Host";
    api<{ username: string }>("GET", "/api/admin/me").then(
      (me) => {
        setUsername(me.username);
        setPhase("ready");
      },
      () => setPhase("login"),
    );
  }, []);

  const socket = useSocket("/ws/admin", phase === "ready", (message) => {
    if (message.type === "admin_state") setState(message as unknown as AdminState);
  });

  useEffect(() => {
    if (socket.closedWith === CLOSE_UNAUTHENTICATED) setPhase("login");
  }, [socket.closedWith]);

  if (phase === "loading") return null;
  if (phase === "login") {
    return (
      <Login
        onLoggedIn={(name) => {
          setUsername(name);
          setPhase("ready");
        }}
      />
    );
  }
  return (
    <div className="shell wide">
      <header className="topbar">
        <strong>LanGamesHub · Host dashboard</strong>
        <span className="topbar-right">
          <span className={`dot ${socket.connected ? "dot-on" : "dot-off"}`} />
          {username}
          <button
            className="secondary small"
            onClick={async () => {
              await api("POST", "/api/admin/logout");
              setPhase("login");
              setState(null);
            }}
          >
            Log out
          </button>
        </span>
      </header>
      {!socket.connected && <p className="banner">Connecting to server…</p>}
      {state ? <Dashboard state={state} /> : <p className="muted">Loading…</p>}
    </div>
  );
}

function Login({ onLoggedIn }: { onLoggedIn: (username: string) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const me = await api<{ username: string }>("POST", "/api/admin/login", { username, password });
      onLoggedIn(me.username);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Invalid username or password" : describeError(err));
    }
  };

  return (
    <main className="centered">
      <div className="card">
        <h1>Host login</h1>
        <form onSubmit={submit} className="stack">
          <input placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
          <input
            type="password"
            autoFocus
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button disabled={!password}>Log in</button>
          {error && <p className="error">{error}</p>}
        </form>
      </div>
    </main>
  );
}
