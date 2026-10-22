import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { BlankScreen } from "../BlankScreen";
import type { PlayerState, SessionInfo } from "../types";
import { Centered, StepsHint, Topbar } from "../ui/Chrome";
import { setHostMuted } from "../ui/sound";
import { useMuted } from "../ui/useSound";
import { Icon, Logo } from "../ui/Icon";
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

  const session = state?.session;

  // Apply the host's mute, and tell the host whether this browser's sound is on.
  const [muted] = useMuted();
  const canReport = phase === "connected" && socket.connected && session?.status === "APPROVED"
    && !!session.nickname && session.screen !== "HIDDEN";
  useEffect(() => setHostMuted(!!session?.sound_muted), [session?.sound_muted]);
  useEffect(() => {
    if (canReport) void api("PUT", "/api/me/sound", { enabled: !muted }).catch(() => {});
  }, [canReport, muted]);

  const inGame = state?.room?.status === "IN_PROGRESS";
  useEffect(() => {
    if (phase !== "connected" || !session || session.screen === "HIDDEN") return;
    document.title = session.nickname ? (inGame ? "Playing · LanGamesHub" : "Lobby · LanGamesHub") : "LanGamesHub";
  }, [phase, session, inGame]);

  if (phase === "loading" || phase === "blank") return <BlankScreen />;
  if (phase === "password") {
    return (
      <PasswordForm
        notice={notice}
        onSubmitted={(next) => {
          setNotice(null);
          setState({ session: next });
          applySession(next);
        }}
      />
    );
  }
  if (phase === "kicked") {
    return (
      <Centered>
        <div className="card-logo"><span className="brand-mark" style={{ background: "var(--grad-warm)" }}><Icon name="plug" size={30} /></span></div>
        <h1>Disconnected</h1>
        <p className="lead">
          {socket.closedWith === CLOSE_TOO_MANY
            ? "LanGamesHub is open in too many tabs of this browser. Close some, then reconnect."
            : "The host disconnected this browser."}
        </p>
        <div className="stack">
          <button className="large block" onClick={() => {
            setPhase("connected");
            setGeneration((g) => g + 1);
          }}>
            <Icon name="refresh" /> Reconnect
          </button>
        </div>
      </Centered>
    );
  }

  // Hidden by the host: show nothing at all (the server also sends nothing else).
  if (!session || session.screen === "HIDDEN") return <BlankScreen />;

  if (session.status === "PENDING") {
    return (
      <Centered>
        <div className="radar" aria-hidden="true"><span /><span /><span /><Logo /></div>
        <h1 style={{ textAlign: "center" }}>Waiting for the host</h1>
        <p className="lead" style={{ textAlign: "center" }}>
          Your request has been sent. This page will continue automatically once the host approves it.
        </p>
        <StepsHint step={2} />
      </Centered>
    );
  }
  if (!session.nickname) return <NicknameForm />;

  return (
    <div className="shell">
      <Topbar connected={socket.connected} name={session.nickname}
        badge={session.is_host ? <span className="badge">host</span> : undefined} />
      {!socket.connected && (
        <p className="banner"><span className="spinner" style={{ width: 16, height: 16, margin: 0, borderWidth: 2 }} />Reconnecting to the host…</p>
      )}
      {state?.room ? (
        <RoomView room={state.room} game={state.game ?? null} me={session} />
      ) : (
        <Lobby lobby={state?.lobby ?? { games: [], rooms: [] }} nickname={session.nickname} />
      )}
    </div>
  );
}
