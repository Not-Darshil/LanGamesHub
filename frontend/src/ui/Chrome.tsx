import type { ReactNode } from "react";
import { Avatar } from "./Avatar";
import { Icon, Logo } from "./Icon";
import { setTheme, useTheme } from "./theme";
import { useHostMuted, useMuted } from "./useSound";

export function SoundToggle() {
  const [muted, setMuted] = useMuted();
  const hostMuted = useHostMuted();
  if (hostMuted) {
    return (
      <span className="host-muted" title="The host has muted sound for everyone in this room" aria-label="Muted by the host">
        <Icon name="volume-x" size={16} /><Icon name="lock" size={11} />
      </span>
    );
  }
  return (
    <button type="button" className="ghost icon-btn" onClick={() => setMuted(!muted)}
      aria-label={muted ? "Unmute sounds" : "Mute sounds"} title={muted ? "Sounds off" : "Sounds on"}>
      <Icon name={muted ? "volume-x" : "volume"} />
    </button>
  );
}

export function ThemeToggle() {
  const theme = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button type="button" className="ghost icon-btn theme-toggle" onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`}>
      <Icon name={theme === "dark" ? "sun" : "moon"} />
    </button>
  );
}

export function ConnectionPill({ connected }: { connected: boolean }) {
  return connected ? (
    <span className="pill ok live" title="Connected to the host">Live</span>
  ) : (
    <span className="pill warn" title="Trying to reconnect"><Icon name="wifi-off" size={14} />Offline</span>
  );
}

export function Topbar({ subtitle, connected, name, badge, children }: {
  subtitle?: string; connected: boolean; name?: string | null; badge?: ReactNode; children?: ReactNode;
}) {
  return (
    <header className="topbar">
      <span className="brand">
        <Logo />
        <span>LanGamesHub {subtitle && <small>· {subtitle}</small>}</span>
      </span>
      <span className="topbar-right">
        <ConnectionPill connected={connected} />
        <ThemeToggle />
        <SoundToggle />
        {name && (
          <span className="me-chip">
            <Avatar name={name} size={30} online={connected} />
            <span className="me-name">{name}</span>
            {badge}
          </span>
        )}
        {children}
      </span>
    </header>
  );
}

/** Full-screen centred card with decorative background, for the entry screens. */
export function Centered({ children }: { children: ReactNode }) {
  return (
    <main className="centered">
      <div className="orbs" aria-hidden="true"><span /><span /><span /></div>
      <div className="corner-tools"><ThemeToggle /></div>
      <div className="card">{children}</div>
    </main>
  );
}

export function StepsHint({ step }: { step: 1 | 2 | 3 }) {
  const steps = ["Password", "Host approval", "Nickname"];
  return (
    <div className="steps-hint" aria-hidden="true">
      {steps.map((label, i) => (
        <span key={label} className={i < step ? "on" : ""}><b>{i + 1 < step ? "✓" : i + 1}</b>{label}</span>
      ))}
    </div>
  );
}
