import { Server, Wifi, WifiOff } from "lucide-react";
import { formatDistanceToNowStrict } from "date-fns";

export function RepeatersPanel({ repeaters, voiceActivity, embedded }) {
  const activeByRpt = new Map();
  (voiceActivity || []).forEach((v) => {
    if (v.repeater_id) activeByRpt.set(v.repeater_id, v);
  });

  return (
    <div data-testid="repeaters-panel" className={embedded ? "px-3 pb-2" : "border-b border-[#2a2a2a] p-3"}>
      {!embedded && (
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">
            Connected MMDVMs
          </div>
          <div className="mono text-[10px] text-neutral-500">{repeaters.length}</div>
        </div>
      )}

      {repeaters.length === 0 && (
        <div className="mono text-[10px] text-neutral-600">
          // waiting for MMDVM connection…
        </div>
      )}

      <div className="space-y-1">
        {repeaters.map((r) => {
          const active = activeByRpt.get(r.repeater_id);
          return (
            <div
              key={r.repeater_id}
              data-testid={`repeater-${r.repeater_id}`}
              className={`border px-2 py-1.5 mono text-[11px] transition-colors ${
                active
                  ? "border-[#39ff14]/60 bg-[#0a1a0a]"
                  : r.authenticated
                  ? "border-[#2a2a2a] bg-black"
                  : "border-[#ffb800]/40 bg-[#1a1005]"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {r.authenticated ? (
                    <Wifi className="h-3 w-3 text-[#39ff14]" />
                  ) : (
                    <WifiOff className="h-3 w-3 text-[#ffb800]" />
                  )}
                  <Server className="h-3 w-3 text-neutral-500" />
                  <span className="text-neutral-100">RPT {r.repeater_id}</span>
                </div>
                {active && (
                  <span
                    className="flex items-center gap-1 text-[9px] text-[#39ff14] uppercase tracking-widest"
                    title={`Voice active from ${active.callsign || "ID " + active.src_id}`}
                  >
                    <span className="relative flex h-2 w-2">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#39ff14] opacity-75" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-[#39ff14]" />
                    </span>
                    TX
                  </span>
                )}
              </div>
              <div className="mt-0.5 flex items-center justify-between text-[10px] text-neutral-500">
                <span>{r.address}</span>
                <span>
                  {r.last_talkgroup ? `TG ${r.last_talkgroup}` : "—"} ·{" "}
                  {r.packets_in ?? 0}/{r.packets_out ?? 0}
                </span>
              </div>
              <div className="text-[10px] text-neutral-600">
                {r.last_seen
                  ? formatDistanceToNowStrict(new Date(r.last_seen)) + " ago"
                  : "—"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
