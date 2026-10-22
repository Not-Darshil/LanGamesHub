import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { BlankScreen } from "../BlankScreen";
import type { PlayerState, SessionInfo } from "../types";
import { CLOSE_FORBIDDEN, CLOSE_KICKED, CLOSE_TOO_MANY, CLOSE_UNAUTHENTICATED, useSocket } from "../useSocket";
import { Lobby } from "./Lobby";
import { NicknameForm } from "./NicknameForm";
import { PasswordForm } from "./PasswordForm";
import { RoomView } from "./RoomView";

type Phase = "loading" | "password" | "blank" | "connected" | "kicked";

/**
 * Guest flow: password → wait for host approval → nickname → lobby → room/game.
 * Everything rendered comes from the server's pushed state; until the server says
 * otherwise (including on first load), the page stays plain white.
 */
export function GuestApp() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [state, setState] = useState<PlayerState | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);

  const applySession = useCallback((session: SessionInfo) => {
    if (session.status === "REJECTED" || session.status === "REVOKED") setPhase("blank");
    else if (session.status === "EXPIRED") setPhase("password");
    else setPhase("connected");
  }, []);

  useEffect(() => {
    api<SessionInfo>("GET", "/api/me").then(
      (session) => {
        setState({ session });
        applySession(session);
      },
      (error) => {
        if (error instanceof ApiError && error.status === 403) setPhase("blank");
        else if (error instanceof ApiError && error.status === 401) setPhase("password");
        else window.setTimeout(() => setGeneration((g) => g + 1), 2000);
      },
    );
  }, [applySession, generation]);

  const socket = useSocket(
    "/ws/player",
    phase === "connected",
    (message) => {
      if (message.type === "state") {
        const next = message as unknown as PlayerState;
        setState(next);
        applySession(next.session);
      }
    },
    generation,
  );

  useEffect(() => {
    if (socket.closedWith === CLOSE_FORBIDDEN) setPhase("blank");
    else if (socket.closedWith === CLOSE_KICKED || socket.closedWith === CLOSE_TOO_MANY) setPhase("kicked");
    else if (socket.closedWith === CLOSE_UNAUTHENTICATED) {
      setNotice("Your session has ended. Enter the password to ask the host again.");
      setPhase("password");
    }
  }, [socket.closedWith]);

  if (phase === "loading" || phase === "blank") return <BlankScreen />;
  if (phase === "password") {
    return (
      <PasswordForm
        notice={notice}
        onSubmitted={(session) => {
          setNotice(null);
          setState({ session });
          applySession(session);
        }}
      />
    );
  }
  if (phase === "kicked") {
    return (
      <Centered>
        <h1>Disconnected</h1>
        <p>
          {socket.closedWith === CLOSE_TOO_MANY
            ? "LanGamesHub is open in too many tabs of this browser. Close some, then reconnect."
            : "The host disconnected this browser."}
        </p>
        <button
          onClick={() => {
            setPhase("connected");
            setGeneration((g) => g + 1);
          }}
        >
          Reconnect
        </button>
      </Centered>
    );
  }

  const session = state?.session;
  // Hidden by the host: show nothing at all (the server also sends nothing else).
  if (!session || session.screen === "HIDDEN") return <BlankScreen />;

  if (session.status === "PENDING") {
    return (
      <Centered>
        <h1>Waiting for the host</h1>
        <p>Your request has been sent. This page will continue automatically once the host
          approves it.</p>
        <div className="spinner" aria-hidden="true" />
      </Centered>
    );
  }
  if (!session.nickname) return <NicknameForm />;

  return (
    <div className="shell">
      <header className="topbar">
        <strong>LanGamesHub</strong>
        <span className="topbar-right">
          <span className={`dot ${socket.connected ? "dot-on" : "dot-off"}`} />
          {session.nickname}
          {session.is_host && <span className="badge">host</span>}
        </span>
      </header>
      {!socket.connected && <p className="banner">Reconnecting to the host…</p>}
      {state?.room ? (
        <RoomView room={state.room} game={state.game ?? null} me={session} />
      ) : (
        <Lobby lobby={state?.lobby ?? { games: [], rooms: [] }} />
      )}
    </div>
  );
}

export function Centered({ children }: { children: React.ReactNode }) {
  return (
    <main className="centered">
      <div className="card">{children}</div>
    </main>
  );
}
