import { useEffect, useState } from "react";

export function BoardClock({ radioCount, connected }) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div data-testid="board-clock" className="border border-[#2a2a2a] bg-black/80 px-3 py-2 text-right mono backdrop-blur">
      <div data-testid="board-clock-time" className="text-2xl font-semibold tabular-nums text-neutral-100 lg:text-3xl">
        {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
      </div>
      <div className="text-[10px] uppercase tracking-[0.25em] text-neutral-500">
        {now.toLocaleDateString([], { weekday: "short", day: "2-digit", month: "short" })}
      </div>
      <div className="mt-1 flex items-center justify-end gap-2 text-[11px]">
        <span className={`h-2 w-2 ${connected ? "bg-[#39ff14]" : "bg-[#ff3b30]"}`} />
        <span data-testid="board-radio-count" className="text-neutral-200">
          {radioCount} radio{radioCount === 1 ? "" : "s"}
        </span>
      </div>
    </div>
  );
}
