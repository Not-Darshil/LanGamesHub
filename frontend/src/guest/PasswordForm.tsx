import { useState, type FormEvent } from "react";
import { ApiError, api, describeError } from "../api";
import type { SessionInfo } from "../types";
import { Centered } from "./GuestApp";

export function PasswordForm({
  notice,
  onSubmitted,
}: {
  notice: string | null;
  onSubmitted: (session: SessionInfo) => void;
}) {
  const [password, setPassword] = useState("");
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
      <h1>LanGamesHub</h1>
      <p>Enter the room password to ask the host for access.</p>
      {notice && <p className="notice">{notice}</p>}
      <form onSubmit={submit} className="stack">
        <input
          type="password"
          autoFocus
          autoComplete="off"
          placeholder="Room password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button disabled={busy || !password}>Request access</button>
        {error && <p className="error">{error}</p>}
      </form>
    </Centered>
  );
}
