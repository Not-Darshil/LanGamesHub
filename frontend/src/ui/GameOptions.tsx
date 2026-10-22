import { Icon } from "./Icon";
import { TimeControlPicker } from "./TimeControlPicker";

/** Room options per game type, mirroring each engine's validate_options. */
export type RoomOptions = Record<string, unknown>;

interface Choice { value: string | number | null; title: string; sub: string; label: string }

const TYPING_LENGTHS: Choice[] = [
  { value: "short", title: "Short", sub: "~120 chars", label: "Short passage" },
  { value: "medium", title: "Medium", sub: "~250 chars", label: "Medium passage" },
  { value: "long", title: "Long", sub: "~400 chars", label: "Long passage" },
];

const BUSINESS_DURATIONS: Choice[] = [
  { value: 30, title: "30", sub: "minutes", label: "30 minute game" },
  { value: 45, title: "45", sub: "minutes", label: "45 minute game" },
  { value: 60, title: "60", sub: "minutes", label: "60 minute game" },
  { value: 90, title: "90", sub: "minutes", label: "90 minute game" },
  { value: null, title: "∞", sub: "until one is left", label: "No time limit" },
];

/** Options a new room of this type starts with. */
export function defaultOptions(gameType: string): RoomOptions {
  if (gameType === "chess") return { time_control: "10+0" };
  if (gameType === "typing") return { length: "medium" };
  if (gameType === "business") return { duration: 60 };
  return {};
}

/** Strips unset values so the server sees only real choices. */
export function cleanOptions(options: RoomOptions): RoomOptions | undefined {
  const entries = Object.entries(options).filter(([, v]) => v !== null && v !== undefined);
  return entries.length ? Object.fromEntries(entries) : undefined;
}

function ChoicePicker({ choices, value, onChange, label }: {
  choices: Choice[]; value: unknown; onChange: (v: Choice["value"]) => void; label: string;
}) {
  return (
    <div className="tc-picker" role="radiogroup" aria-label={label}>
      {choices.map((c) => (
        <button key={String(c.value)} type="button" role="radio" aria-checked={value === c.value} aria-label={c.label}
          className={`tc-option${value === c.value ? " active" : ""}`} onClick={() => onChange(c.value)}>
          <strong>{c.title}</strong>
          <small>{c.sub}</small>
        </button>
      ))}
    </div>
  );
}

/** The options section of a create/propose room form, or nothing for games without options. */
export function GameOptionsPicker({ gameType, value, onChange }: {
  gameType: string; value: RoomOptions; onChange: (next: RoomOptions) => void;
}) {
  if (gameType === "chess") {
    return (
      <div className="field">
        <span>Time control</span>
        <TimeControlPicker value={(value.time_control as string | null | undefined) ?? null}
          onChange={(v) => onChange({ time_control: v })} />
      </div>
    );
  }
  if (gameType === "typing") {
    return (
      <div className="field">
        <span>Passage length</span>
        <ChoicePicker label="Passage length" choices={TYPING_LENGTHS} value={value.length ?? "medium"}
          onChange={(v) => onChange({ length: v })} />
      </div>
    );
  }
  if (gameType === "business") {
    return (
      <div className="field">
        <span><Icon name="clock" size={12} /> Game length</span>
        <ChoicePicker label="Game length" choices={BUSINESS_DURATIONS} value={value.duration ?? null}
          onChange={(v) => onChange({ duration: v })} />
      </div>
    );
  }
  return null;
}
