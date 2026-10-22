import { TIME_CONTROLS } from "./games";
import { Icon } from "./Icon";

/** Segmented picker for chess time controls. `null` = no clock. */
export function TimeControlPicker({ value, onChange }: { value: string | null; onChange: (v: string | null) => void }) {
  return (
    <div className="tc-picker" role="radiogroup" aria-label="Time control">
      {TIME_CONTROLS.map((tc) => (
        <button key={tc.key} type="button" role="radio" aria-checked={value === tc.key}
          aria-label={`${tc.minutes} min${tc.increment ? ` + ${tc.increment}s` : ""} ${tc.kind}`}
          className={`tc-option${value === tc.key ? " active" : ""}`} onClick={() => onChange(tc.key)}>
          <strong>{tc.minutes}{tc.increment ? ` + ${tc.increment}` : ""}</strong>
          <small>{tc.minutes} min{tc.increment ? ` +${tc.increment}s` : ""}</small>
          <em>{tc.kind}</em>
        </button>
      ))}
      <button type="button" role="radio" aria-checked={value === null} aria-label="No clock"
        className={`tc-option${value === null ? " active" : ""}`} onClick={() => onChange(null)}>
        <strong><Icon name="clock" size={18} /></strong>
        <small>No clock</small>
        <em>Casual</em>
      </button>
    </div>
  );
}
