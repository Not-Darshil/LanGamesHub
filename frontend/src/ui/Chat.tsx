import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { api, describeError } from "../api";
import type { ChatMessage, ChatReaction, RoomDetail } from "../types";
import { Avatar } from "./Avatar";
import { useFeedback } from "./Feedback";
import { Icon } from "./Icon";
import { play } from "./sound";

/** The same set as backend app/services/chat.py REACTIONS; the first five are the quick bar. */
export const REACTIONS = ["👍", "😂", "🔥", "👏", "🎉", "😮", "😢", "😡", "❤️", "🤯"];
const MAX_LENGTH = 300;

interface Floater { key: number; emoji: string; name: string; left: number; drift: number }

/**
 * Room chat dock: quick reactions that float across everyone's screen, and a slide-up
 * chat panel. Lives in the corner of every room (waiting room, game and results).
 */
export function RoomChat({ room, meId }: { room: RoomDetail; meId: number }) {
  const { toast } = useFeedback();
  const me = String(meId);
  const enabled = room.chat_enabled !== false;
  const messages = room.chat?.messages ?? [];
  const reactions = room.chat?.reactions ?? [];
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [unread, setUnread] = useState(0);
  const [preview, setPreview] = useState<ChatMessage | null>(null);
  const [floaters, setFloaters] = useState<Floater[]>([]);
  const listRef = useRef<HTMLOListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Everything already in the room when we arrive is history: only newer items alert.
  const lastMessage = useRef(messages.at(-1)?.id ?? 0);
  const lastReaction = useRef(reactions.at(-1)?.id ?? 0);

  useEffect(() => {
    const fresh = messages.filter((m) => m.id > lastMessage.current);
    if (fresh.length === 0) return;
    lastMessage.current = fresh.at(-1)!.id;
    const fromOthers = fresh.filter((m) => m.from !== me);
    if (fromOthers.length === 0) return;
    if (!open) {
      setUnread((n) => n + fromOthers.length);
      setPreview(fromOthers.at(-1)!);
      play("pop");
    }
  }, [messages, me, open]);

  useEffect(() => {
    if (!preview) return;
    const timer = window.setTimeout(() => setPreview(null), 4000);
    return () => window.clearTimeout(timer);
  }, [preview]);

  useEffect(() => {
    const fresh = reactions.filter((r) => r.id > lastReaction.current);
    if (fresh.length === 0) return;
    lastReaction.current = fresh.at(-1)!.id;
    spawn(fresh);
    if (fresh.some((r) => r.from !== me)) play("pop");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reactions, me]);

  const spawn = (items: ChatReaction[]) => {
    const made = items.map((r, i) => ({
      key: r.id, emoji: r.emoji, name: r.from === me ? "You" : r.nickname,
      left: 34 + Math.random() * 30 + i * 2, drift: (Math.random() - 0.5) * 140,
    }));
    setFloaters((list) => [...list.slice(-20), ...made]);
    window.setTimeout(() => setFloaters((list) => list.filter((f) => !made.some((m) => m.key === f.key))), 3200);
  };

  // The host turning chat off closes the panel; it stays closed when chat comes back.
  useEffect(() => {
    if (!enabled) setOpen(false);
  }, [enabled]);

  useLayoutEffect(() => {
    if (open) listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [open, messages.length]);

  useEffect(() => {
    if (!open) return;
    setUnread(0);
    setPreview(null);
    inputRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const send = async (event: FormEvent) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      await api("POST", `/api/rooms/${room.id}/chat`, { text });
      setDraft("");
    } catch (err) {
      toast(describeError(err), "error");
    } finally {
      setSending(false);
      inputRef.current?.focus({ preventScroll: true });
    }
  };

  const react = async (emoji: string) => {
    try {
      await api("POST", `/api/rooms/${room.id}/react`, { emoji });
    } catch (err) {
      toast(describeError(err), "error");
    }
  };

  const floating = (
    <div className="reaction-layer" aria-hidden="true">
      {floaters.map((f) => (
        <span key={f.key} className="reaction-float" style={{ left: `${f.left}%`, ["--drift" as string]: `${f.drift}px` }}>
          <span className="reaction-emoji">{f.emoji}</span>
          <span className="reaction-name">{f.name}</span>
        </span>
      ))}
    </div>
  );

  if (!enabled) {
    return (
      <div className="chat-dock">
        <span className="pill" title="The host has turned chat off"><Icon name="lock" size={13} />Chat is off</span>
      </div>
    );
  }

  return (
    <>
      {floating}
      <div className={`chat-dock${open ? " open" : ""}`}>
        {open && (
          <section className="chat-panel" role="dialog" aria-label="Room chat">
            <header className="chat-head">
              <strong><Icon name="mail" size={16} />Room chat</strong>
              <span className="muted small-print">{room.members.length} in room</span>
              <button type="button" className="ghost icon-btn small" aria-label="Close chat" onClick={() => setOpen(false)}>
                <Icon name="x" size={16} />
              </button>
            </header>
            <ol className="chat-list" ref={listRef} aria-live="polite">
              {messages.length === 0 && (
                <li className="chat-empty">
                  <span>👋</span>
                  No messages yet. Say hi!
                </li>
              )}
              {messages.map((m, i) => {
                const mine = m.from === me;
                const grouped = i > 0 && messages[i - 1]!.from === m.from;
                return (
                  <li key={m.id} className={`chat-msg${mine ? " mine" : ""}${grouped ? " grouped" : ""}`}>
                    {!mine && !grouped && <Avatar name={m.nickname} size={26} />}
                    <div className="chat-bubble-wrap">
                      {!mine && !grouped && <span className="chat-name">{m.nickname}</span>}
                      <span className="chat-bubble" title={new Date(m.at).toLocaleTimeString()}>{m.text}</span>
                    </div>
                  </li>
                );
              })}
            </ol>
            <div className="chat-reactions" role="group" aria-label="Reactions">
              {REACTIONS.map((emoji) => (
                <button key={emoji} type="button" aria-label={`React ${emoji}`} onClick={() => void react(emoji)}>{emoji}</button>
              ))}
            </div>
            <form className="chat-form" onSubmit={send}>
              <input ref={inputRef} value={draft} maxLength={MAX_LENGTH} placeholder="Message the room…"
                aria-label="Chat message" onChange={(e) => setDraft(e.target.value)} />
              <button aria-label="Send message" disabled={!draft.trim() || sending}><Icon name="arrow-left" size={16} className="send-icon" /></button>
            </form>
            {draft.length > MAX_LENGTH - 40 && <span className="chat-count">{MAX_LENGTH - draft.length}</span>}
          </section>
        )}
        {!open && preview && (
          <button type="button" className="chat-preview" onClick={() => setOpen(true)}>
            <Avatar name={preview.nickname} size={22} />
            <span><strong>{preview.nickname}</strong> {preview.text}</span>
          </button>
        )}
        <div className="chat-bar">
          <div className="quick-reactions" role="group" aria-label="Quick reactions">
            {REACTIONS.slice(0, 5).map((emoji) => (
              <button key={emoji} type="button" aria-label={`React ${emoji}`} onClick={() => void react(emoji)}>{emoji}</button>
            ))}
          </div>
          <button type="button" className={`chat-toggle${open ? " active" : ""}`} aria-label={open ? "Close chat" : "Open chat"}
            aria-expanded={open} onClick={() => setOpen(!open)}>
            <Icon name="mail" size={18} />
            <span className="chat-toggle-label">Chat</span>
            {unread > 0 && <span className="chat-unread">{unread > 9 ? "9+" : unread}</span>}
          </button>
        </div>
      </div>
    </>
  );
}
