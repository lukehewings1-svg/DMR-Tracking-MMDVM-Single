import { useEffect, useRef } from "react";

const COLORS = {
  "Motorola LRRP": "text-[#39ff14]",
  "Hytera RRS": "text-[#00f0ff]",
  NMEA: "text-[#ffb800]",
  APRS: "text-[#c084fc]",
  SIMULATED: "text-neutral-400",
};

function shortTime(iso) {
  if (!iso) return "--:--:--";
  try {
    return new Date(iso).toISOString().substring(11, 19);
  } catch {
    return "--:--:--";
  }
}

export function PacketLog({ packets, embedded }) {
  const boxRef = useRef(null);
  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = 0;
  }, [packets.length]);

  return (
    <div
      data-testid="packet-log"
      className={`flex h-full min-h-0 flex-col ${embedded ? "bg-black" : "border-t border-[#2a2a2a] bg-black"}`}
    >
      {!embedded && (
        <div className="flex items-center justify-between border-b border-[#2a2a2a] px-3 py-1.5">
          <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">
            Raw Packet Log
          </div>
          <div className="mono text-[10px] text-neutral-500">
            {packets.length} pkt
          </div>
        </div>
      )}
      <div
        ref={boxRef}
        className="flex-1 overflow-y-auto p-2 mono text-[11px] leading-relaxed"
      >
        {packets.length === 0 && (
          <div className="text-neutral-700">// waiting for packets…</div>
        )}
        {packets.map((p) => {
          const c = COLORS[p.format] || "text-neutral-300";
          return (
            <div
              key={p.id}
              data-testid={`packet-row-${p.id}`}
              className="whitespace-nowrap"
            >
              <span className="text-neutral-600">{shortTime(p.timestamp)}</span>{" "}
              <span className={`${c}`}>[{p.format}]</span>{" "}
              <span className="text-neutral-400">{p.source || "?"}</span>{" "}
              <span className="text-neutral-100">ID {p.dmr_id}</span>
              {p.callsign && (
                <span className="text-neutral-300"> {p.callsign}</span>
              )}{" "}
              <span className="text-neutral-500">
                {p.lat?.toFixed(5)}, {p.lon?.toFixed(5)}
              </span>
              {p.speed != null && (
                <span className="text-neutral-500"> {p.speed}kph</span>
              )}
              {p.heading != null && (
                <span className="text-neutral-500"> @{p.heading}°</span>
              )}
              {p.hex_preview && (
                <span className="text-neutral-700"> · {p.hex_preview}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
