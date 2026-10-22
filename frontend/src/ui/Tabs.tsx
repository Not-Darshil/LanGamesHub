import { useLayoutEffect, useRef, useState } from "react";

export interface TabDef<K extends string> { key: K; label: string; count?: number }

/** Segmented tab bar with a sliding indicator. */
export function Tabs<K extends string>({ tabs, value, onChange, label }: {
  tabs: TabDef<K>[]; value: K; onChange: (key: K) => void; label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState<{ left: number; width: number } | null>(null);
  useLayoutEffect(() => {
    const el = ref.current?.querySelector<HTMLElement>(`[data-key="${CSS.escape(value)}"]`);
    if (el) setIndicator({ left: el.offsetLeft, width: el.offsetWidth });
  }, [value, tabs.length, tabs.map((t) => `${t.label}${t.count ?? ""}`).join("|")]);
  return (
    <div className="tabs" role="tablist" aria-label={label} ref={ref}>
      {indicator && <span className="tabs-indicator" style={{ transform: `translateX(${indicator.left}px)`, width: indicator.width }} />}
      {tabs.map((t) => (
        <button key={t.key} type="button" role="tab" data-key={t.key} aria-selected={t.key === value}
          className={t.key === value ? "active" : ""} onClick={() => onChange(t.key)}>
          {t.label}
          {t.count !== undefined && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}
