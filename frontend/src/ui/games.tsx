/** Presentation metadata for each game type: icon, colours, tagline. */
export interface GameMeta { icon: string; gradient: string; tagline: string }

const META: Record<string, GameMeta> = {
  uno: { icon: "🃏", gradient: "linear-gradient(135deg, #ef4444, #f59e0b)", tagline: "Match colours, stack +2s and shout UNO." },
  chess: { icon: "♞", gradient: "linear-gradient(135deg, #64748b, #1e293b)", tagline: "The classic. Now with bullet to classical clocks." },
  ludo: { icon: "🎲", gradient: "linear-gradient(135deg, #22c55e, #3b82f6)", tagline: "Race your four tokens home. Sixes roll again." },
  snakes: { icon: "🐍", gradient: "linear-gradient(135deg, #84cc16, #f59e0b)", tagline: "Climb ladders, dodge snakes, land on 100." },
  battleship: { icon: "⚓", gradient: "linear-gradient(135deg, #0ea5e9, #6366f1)", tagline: "Hide your fleet. Hunt theirs. Sink them all." },
};

const FALLBACK: GameMeta = { icon: "🎮", gradient: "linear-gradient(135deg, #8b5cf6, #6366f1)", tagline: "" };

export function gameMeta(gameType: string): GameMeta {
  return META[gameType] ?? FALLBACK;
}

export function GameIcon({ gameType, size }: { gameType: string; size?: "small" | "large" }) {
  const meta = gameMeta(gameType);
  return (
    <span className={`game-icon${size ? ` ${size}` : ""}`} style={{ ["--tile" as string]: meta.gradient }} aria-hidden="true">
      {gameType === "chess" ? "♞︎" : meta.icon}
    </span>
  );
}

/** Chess time controls, mirroring backend app/games/chess_game.py TIME_CONTROLS. */
export const TIME_CONTROLS: { key: string; minutes: number; increment: number; kind: string }[] = [
  { key: "1+0", minutes: 1, increment: 0, kind: "Bullet" },
  { key: "3+2", minutes: 3, increment: 2, kind: "Blitz" },
  { key: "5+0", minutes: 5, increment: 0, kind: "Blitz" },
  { key: "10+0", minutes: 10, increment: 0, kind: "Rapid" },
  { key: "15+10", minutes: 15, increment: 10, kind: "Rapid" },
  { key: "30+0", minutes: 30, increment: 0, kind: "Classical" },
];
