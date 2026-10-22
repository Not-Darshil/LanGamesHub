/** Initials avatar with a stable gradient derived from the name. */
const GRADIENTS = [
  ["#8b5cf6", "#6366f1"], ["#f43f5e", "#f97316"], ["#10b981", "#06b6d4"], ["#f59e0b", "#ef4444"],
  ["#3b82f6", "#22d3ee"], ["#ec4899", "#8b5cf6"], ["#14b8a6", "#84cc16"], ["#6366f1", "#ec4899"],
];

function hash(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return h;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return [...parts[0]!].slice(0, 2).join("").toUpperCase();
  return ((parts[0]![0] ?? "") + (parts[parts.length - 1]![0] ?? "")).toUpperCase();
}

export function avatarGradient(name: string): string {
  const [a, b] = GRADIENTS[hash(name) % GRADIENTS.length]!;
  return `linear-gradient(135deg, ${a}, ${b})`;
}

export function Avatar({ name, size = 32, color, online, ring, title }: {
  name: string; size?: number; color?: string; online?: boolean; ring?: boolean; title?: string;
}) {
  return (
    <span className={`avatar${ring ? " ring" : ""}`} title={title ?? name}
      style={{ ["--size" as string]: `${size}px`, background: color ?? avatarGradient(name) }}>
      {initials(name)}
      {online !== undefined && <span className={`avatar-status${online ? " on" : ""}`} />}
    </span>
  );
}
