import { useState, type FormEvent } from "react";
import { api, describeError } from "../api";
import { Centered } from "./GuestApp";

export function NicknameForm() {
  const [nickname, setNickname] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await api("PUT", "/api/me/nickname", { nickname });
      // The server pushes the updated session over the socket.
    } catch (err) {
      setError(describeError(err));
    }
  };

  return (
    <Centered>
      <h1>You're in!</h1>
      <p>Choose the name other players will see.</p>
      <form onSubmit={submit} className="stack">
        <input
          autoFocus
          maxLength={20}
          placeholder="Nickname"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
        />
        <button disabled={!nickname.trim()}>Continue</button>
        {error && <p className="error">{error}</p>}
      </form>
    </Centered>
  );
}
