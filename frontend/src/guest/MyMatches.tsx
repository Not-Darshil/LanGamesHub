import { useEffect, useState } from "react";
import { api, describeError } from "../api";
import type { HistoryEntry } from "../types";
import { Icon } from "../ui/Icon";
import { MatchRow, MatchViewer } from "../ui/MatchViewer";
import { Tabs } from "../ui/Tabs";

/** The matches this player took part in, with their place; each opens the end screen. */
export function MyMatches({ refreshKey }: { refreshKey: number }) {
  const [matches, setMatches] = useState<HistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    let live = true;
    api<{ matches: HistoryEntry[] }>("GET", "/api/history").then(
      (r) => live && setMatches(r.matches),
      (e) => live && setError(describeError(e)),
    );
    return () => { live = false; };
  }, [refreshKey]);

  if (error) return <p className="error">{error}</p>;
  if (!matches) return <div className="spinner" />;
  if (matches.length === 0) {
    return (
      <div className="empty">
        <span className="empty-icon"><Icon name="trophy" size={26} /></span>
        <strong>No matches yet</strong>
        <span>Games you finish show up here with your placing and the final position.</span>
      </div>
    );
  }

  const wins = matches.filter((m) => m.my_place === 1 && m.outcome === "WIN").length;
  const podiums = matches.filter((m) => (m.outcome === "WIN" || m.outcome === "DRAW") && !!m.my_place && m.my_place <= 3).length;
  const games = [...new Map(matches.map((m) => [m.game_type, m.game_name])).entries()];
  const shown = filter === "all" ? matches : matches.filter((m) => m.game_type === filter);
  return (
    <div>
      <div className="stat-grid">
        <div className="stat accent"><span className="stat-icon"><Icon name="gamepad" size={20} /></span><div><strong>{matches.length}</strong><span>Matches played</span></div></div>
        <div className="stat ok"><span className="stat-icon"><Icon name="trophy" size={20} /></span><div><strong>{wins}</strong><span>Wins</span></div></div>
        <div className="stat warn"><span className="stat-icon"><Icon name="medal" size={20} /></span><div><strong>{podiums}</strong><span>Top-3 finishes</span></div></div>
      </div>
      {games.length > 1 && (
        <div style={{ marginBottom: 12 }}>
          <Tabs label="Filter by game" value={filter} onChange={setFilter} tabs={[
            { key: "all", label: "All", count: matches.length },
            ...games.map(([type, name]) => ({ key: type, label: name, count: matches.filter((m) => m.game_type === type).length })),
          ]} />
        </div>
      )}
      <ul key={filter} className="match-list tab-panel">
        {shown.map((m, i) => <li key={m.id}><MatchRow match={m} index={i} mine onOpen={() => setOpen(m.id)} /></li>)}
      </ul>
      {open !== null && <MatchViewer url={`/api/history/${open}`} onClose={() => setOpen(null)} />}
    </div>
  );
}
