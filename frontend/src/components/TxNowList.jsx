import { Mic } from "lucide-react";

export function TxNowList({ voiceActivity, groups, radios, className = "" }) {
  const items = voiceActivity || [];
  const groupByTg = new Map((groups || []).map((g) => [g.talkgroup_id, g]));
  const radioById = new Map((radios || []).map((r) => [r.dmr_id, r]));
  return (
    <div data-testid="tx-now-list" className={`border border-[#2a2a2a] bg-black/80 mono text-[11px] backdrop-blur ${className}`}>
      <div className="flex items-center gap-1.5 border-b border-[#2a2a2a] px-2 py-1 text-[9px] uppercase tracking-[0.3em] text-neutral-500">
        <Mic className="h-3 w-3" /> Transmitting now
      </div>
      {items.length === 0 ? (
        <div className="px-2 py-1.5 text-neutral-600">// channel quiet</div>
      ) : (
        items.map((v) => {
          const g = groupByTg.get(v.talkgroup_id);
          const name = v.callsign || radioById.get(v.src_id)?.callsign || `ID ${v.src_id}`;
          return (
            <div key={`${v.talkgroup_id}-${v.src_id}`} data-testid={`tx-now-${v.src_id}`} className="flex items-center gap-2 px-2 py-1">
              <span className="h-2 w-2 shrink-0 bg-[#39ff14] shadow-[0_0_8px_#39ff14]" style={{ animation: "emergency-ring 0.5s ease-in-out infinite alternate" }} />
              <span className="truncate text-neutral-100">{name}</span>
              <span className="ml-auto shrink-0 text-neutral-500" style={{ color: g?.color }}>
                {g ? g.name : `TG ${v.talkgroup_id}`}
              </span>
            </div>
          );
        })
      )}
    </div>
  );
}
