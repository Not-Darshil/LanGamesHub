import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api, describeError } from "../api";
import type { AdminState } from "../types";
import { Centered, Topbar } from "../ui/Chrome";
import { Icon, Logo } from "../ui/Icon";
import { CLOSE_UNAUTHENTICATED, useSocket } from "../useSocket";
import { Dashboard } from "./Dashboard";

type Phase = "loading" | "login" | "ready";

export function AdminApp() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [username, setUsername] = useState<string | null>(null);
  const [state, setState] = useState<AdminState | null>(null);

  useEffect(() => {
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

  // Pending requests show in the tab title so the host notices them from another tab.
  const pending = state?.pending.length ?? 0;
  useEffect(() => {
    document.title = pending > 0 ? `(${pending}) Access requests · LanGamesHub Host` : "LanGamesHub · Host";
  }, [pending]);

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
      <Topbar subtitle="Host dashboard" connected={socket.connected} name={username}>
        <button
          className="secondary small"
          onClick={async () => {
            await api("POST", "/api/admin/logout");
            setPhase("login");
            setState(null);
          }}
        >
          <Icon name="logout" size={14} />Log out
        </button>
      </Topbar>
      {!socket.connected && <p className="banner">Connecting to server…</p>}
      {state ? <Dashboard state={state} /> : <div className="spinner" />}
    </div>
  );
}

function Login({ onLoggedIn }: { onLoggedIn: (username: string) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const me = await api<{ username: string }>("POST", "/api/admin/login", { username, password });
      onLoggedIn(me.username);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Invalid username or password" : describeError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Centered>
      <div className="card-logo"><Logo /></div>
      <h1 style={{ textAlign: "center" }}>Host login</h1>
      <p className="lead" style={{ textAlign: "center" }}>Approve guests, open rooms and start matches.</p>
      <form onSubmit={submit} className="stack">
        <div className="input-wrap">
          <Icon name="user" />
          <input className="large" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
        </div>
        <div className="input-wrap">
          <Icon name="key" />
          <input
            className="large"
            type="password"
            autoFocus
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button className="large block" disabled={!password || busy}>Log in</button>
        {error && <p className="error">{error}</p>}
      </form>
    </Centered>
  );
}
