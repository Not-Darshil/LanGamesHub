import { useState, type FormEvent } from "react";
import { api, describeError } from "../api";
import { Avatar } from "../ui/Avatar";
import { Centered, StepsHint } from "../ui/Chrome";

const IDEAS = ["Maverick", "Pixel", "Nova", "Blaze", "Rook", "Ace", "Echo", "Viper"];

export function NicknameForm() {
  const [nickname, setNickname] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("PUT", "/api/me/nickname", { nickname });
      // The server pushes the updated session over the socket.
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  const preview = nickname.trim() || "?";
  return (
    <Centered>
      <div className="name-preview">
        <Avatar key={preview.slice(0, 2)} name={preview} size={72} />
      </div>
      <h1 style={{ textAlign: "center" }}>You're in!</h1>
      <p className="lead" style={{ textAlign: "center" }}>Choose the name other players will see.</p>
      <form onSubmit={submit} className="stack">
        <input
          className="large"
          autoFocus
          maxLength={20}
          placeholder="Nickname"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
        />
        <div className="chips">
          {IDEAS.map((idea) => (
            <button key={idea} type="button" className="secondary" onClick={() => setNickname(idea)}>{idea}</button>
          ))}
        </div>
        <button className="large block" disabled={!nickname.trim() || busy}>Continue</button>
        {error && <p className="error">{error}</p>}
      </form>
      <StepsHint step={3} />
    </Centered>
  );
}
