import { formatDistanceToNowStrict } from "date-fns";
import { iconFor } from "@/lib/icons";

function relTime(iso) {
  if (!iso) return "—";
  try {
    return formatDistanceToNowStrict(new Date(iso)) + " ago";
  } catch {
    return "—";
  }
}

function RssiBar({ rssi }) {
  const v = rssi ?? 0;
  const bars = 4;
  const filled = Math.max(0, Math.min(bars, Math.round(((v + 120) / 60) * bars)));
  return (
    <div className="flex items-end gap-[2px]" title={`RSSI ${rssi ?? "?"}`}>
      {Array.from({ length: bars }).map((_, i) => (
        <span
          key={i}
          className="w-[3px]"
          style={{
            height: `${4 + i * 3}px`,
            background: i < filled ? "#39ff14" : "#2a2a2a",
          }}
        />
      ))}
    </div>
  );
}

export function Roster({ radios, selectedId, onSelect, consumeFlash, onOpenDetail }) {
  return (
    <aside
      data-testid="roster"
      className="flex h-full flex-col border-r border-[#2a2a2a] bg-[#0a0a0a]"
    >
      <div className="flex items-center justify-between border-b border-[#2a2a2a] px-3 py-2">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">
            Radio Roster
          </div>
          <div className="mono text-xs text-neutral-300">
            {radios.length} contact{radios.length === 1 ? "" : "s"}
          </div>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto" data-testid="roster-list">
        {radios.length === 0 && (
          <div className="p-6 text-center mono text-[11px] text-neutral-600">
            No radios heard yet.
            <br />
            Point MMDVMHost DMR-Network at this host, or use the injector →
          </div>
        )}
        {radios.map((r) => {
          const flash = consumeFlash(r.dmr_id);
          const selected = r.dmr_id === selectedId;
          const color = r.color || "#39ff14";
          const IconComp = iconFor(r.icon);
          return (
            <div
              key={r.dmr_id}
              data-testid={`roster-row-${r.dmr_id}`}
              onClick={() => onSelect(r.dmr_id)}
              onDoubleClick={() => onOpenDetail?.(r.dmr_id)}
              className={`cursor-pointer border-b border-[#1a1a1a] px-3 py-2 transition-colors ${
                selected
                  ? "bg-[#001a1f] border-l-2 border-l-[#00f0ff]"
                  : "hover:bg-[#111]"
              } ${flash ? "row-flash" : ""}`}
              title="Click to focus map · Double-click for details"
            >
              <div className="flex items-center gap-2">
                <div
                  className="flex h-7 w-7 items-center justify-center border shrink-0"
                  style={{ color, borderColor: color + "55" }}
                >
                  <IconComp className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="mono text-sm font-semibold text-neutral-100 truncate">
                      {r.callsign || (
                        <span className="text-neutral-600">— no call —</span>
                      )}
                    </div>
                    <RssiBar rssi={r.last_rssi} />
                  </div>
                  <div className="mono text-[10px] text-neutral-500">
                    ID {r.dmr_id} · {r.last_format || "?"}
                  </div>
                </div>
              </div>
              <div className="mt-1 flex items-center justify-between mono text-[10px] text-neutral-500">
                <span>
                  {r.last_lat?.toFixed(4)}, {r.last_lon?.toFixed(4)}
                </span>
                <span className="text-neutral-400">{relTime(r.last_seen)}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="border-t border-[#2a2a2a] px-3 py-2 mono text-[10px] text-neutral-600">
        Double-click a row to edit call sign & icon
      </div>
    </aside>
  );
}
