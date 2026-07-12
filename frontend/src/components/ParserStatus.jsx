import { useMemo } from "react";

export function ParserStatus({ packets, parsers }) {
  const activity = useMemo(() => {
    const now = Date.now();
    const counts = {};
    const recent = {};
    (parsers || []).forEach((p) => {
      counts[p] = 0;
      recent[p] = false;
    });
    packets.forEach((p) => {
      counts[p.format] = (counts[p.format] || 0) + 1;
      const t = p.timestamp ? new Date(p.timestamp).getTime() : 0;
      if (now - t < 8000) recent[p.format] = true;
    });
    return { counts, recent };
  }, [packets, parsers]);

  return (
    <div data-testid="parser-status" className="border-b border-[#2a2a2a] p-3">
      <div className="mb-2 text-[10px] uppercase tracking-[0.3em] text-neutral-500">
        Parsers
      </div>
      <div className="grid grid-cols-2 gap-2 mono">
        {(parsers || []).map((name) => {
          const c = activity.counts[name] || 0;
          const on = c > 0;
          const live = activity.recent[name];
          return (
            <div
              key={name}
              data-testid={`parser-${name.toLowerCase().replace(/\s+/g, "-")}`}
              className={`flex items-center justify-between border px-2 py-1.5 text-[11px] transition-colors ${
                on
                  ? "border-[#39ff14]/40 bg-[#0a1a0a]"
                  : "border-[#2a2a2a] bg-[#0a0a0a]"
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    live
                      ? "bg-[#39ff14] shadow-[0_0_6px_#39ff14] animate-pulse"
                      : on
                      ? "bg-[#39ff14]"
                      : "bg-[#3a3a3a]"
                  }`}
                />
                <span className="text-neutral-200">{name}</span>
              </div>
              <span className="text-neutral-400">{c}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
