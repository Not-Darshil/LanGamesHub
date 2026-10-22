import { useState, type FormEvent } from "react";
import { ApiError, api, describeError } from "../api";
import type { SessionInfo } from "../types";
import { Centered, StepsHint } from "../ui/Chrome";
import { Icon, Logo } from "../ui/Icon";

export function PasswordForm({
  notice,
  onSubmitted,
}: {
  notice: string | null;
  onSubmitted: (session: SessionInfo) => void;
}) {
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSubmitted(await api<SessionInfo>("POST", "/api/access/request", { password }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        onSubmitted({ id: 0, status: "REJECTED", screen: "VISIBLE" });
      } else {
        setError(describeError(err));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Centered>
      <div className="card-logo"><Logo /></div>
      <h1 style={{ textAlign: "center" }}>LanGamesHub</h1>
      <p className="lead" style={{ textAlign: "center" }}>Enter the room password to ask the host for access.</p>
      {notice && <p className="notice">{notice}</p>}
      <form onSubmit={submit} className="stack">
        <div className="input-wrap">
          <Icon name="key" />
          <input
            className="large"
            type={show ? "text" : "password"}
            autoFocus
            autoComplete="off"
            placeholder="Room password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button type="button" className="ghost icon-btn small input-action" onClick={() => setShow(!show)}
            aria-label={show ? "Hide password" : "Show password"}>
            <Icon name={show ? "eye-off" : "eye"} size={16} />
          </button>
        </div>
        <button className="large block" disabled={busy || !password}>
          {busy ? <span className="spinner" style={{ width: 18, height: 18, margin: 0, borderWidth: 2 }} /> : null}
          Request access
        </button>
        {error && <p className="error" style={{ animation: "shake 0.4s" }}>{error}</p>}
      </form>
      <StepsHint step={1} />
    </Centered>
  );
}
