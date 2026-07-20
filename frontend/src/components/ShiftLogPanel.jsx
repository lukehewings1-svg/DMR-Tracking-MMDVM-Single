import { useEffect, useState } from "react";
import { format } from "date-fns";
import {
  Download,
  Trash2,
  Filter,
  Clock,
  AlertOctagon,
  MessageSquare,
  MapPin,
  Radio,
  Bell,
  RefreshCw,
} from "lucide-react";
import { listShiftLog, shiftLogCsvUrl, clearShiftLog } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

const EVENT_LABEL = {
  position: { label: "POS", color: "#39ff14", Icon: MapPin },
  emergency: { label: "EMERG", color: "#ff3b30", Icon: AlertOctagon },
  emergency_cleared: { label: "CLEAR", color: "#ffb800", Icon: AlertOctagon },
  message_in: { label: "MSG⇐", color: "#00f0ff", Icon: MessageSquare },
  message_out: { label: "MSG⇒", color: "#c084fc", Icon: MessageSquare },
  voice: { label: "VOICE", color: "#39ff14", Icon: Radio },
  alert: { label: "GEO", color: "#ffb800", Icon: Bell },
  radio_update: { label: "EDIT", color: "#9ca3af", Icon: Radio },
};

const FILTERS = [
  { key: null, label: "All" },
  { key: "emergency", label: "Emerg" },
  { key: "voice", label: "Voice" },
  { key: "message_in", label: "Msg In" },
  { key: "message_out", label: "Msg Out" },
  { key: "alert", label: "Geo" },
  { key: "position", label: "Pos" },
];

export function ShiftLogPanel({ liveEntry }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin" || user?.role === "super_admin";
  const [entries, setEntries] = useState([]);
  const [filter, setFilter] = useState(null);
  const [loading, setLoading] = useState(false);

  const reload = async () => {
    setLoading(true);
    try {
      setEntries(await listShiftLog({ limit: 300, ...(filter ? { event_type: filter } : {}) }));
    } catch (e) {
      toast.error("Failed to load shift log");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  // Prepend WS-live entries in real time
  useEffect(() => {
    if (!liveEntry) return;
    if (filter && liveEntry.event_type !== filter) return;
    setEntries((prev) =>
      prev.some((e) => e.id === liveEntry.id) ? prev : [liveEntry, ...prev].slice(0, 500)
    );
  }, [liveEntry, filter]);

  const download = async () => {
    const { url, token } = shiftLogCsvUrl(filter ? { event_type: filter } : {});
    try {
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error("CSV export failed");
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = res.headers.get("Content-Disposition")?.match(/filename="?([^"]+)/)?.[1] || "shift-log.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      toast.error(e.message || "CSV export failed");
    }
  };

  const clear = async () => {
    if (!window.confirm("Clear the entire shift log? This cannot be undone.")) return;
    await clearShiftLog();
    setEntries([]);
    toast.success("Shift log cleared");
  };

  return (
    <div className="flex h-full flex-col bg-[#0a0a0a]" data-testid="shift-log-panel">
      <div className="flex items-center justify-between border-b border-[#2a2a2a] px-3 py-2">
        <div className="flex items-center gap-2">
          <Clock className="h-3.5 w-3.5 text-[#00f0ff]" />
          <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">
            Shift Log
          </div>
          <span className="mono text-[10px] text-neutral-500">
            {entries.length}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            data-testid="shift-log-refresh"
            onClick={reload}
            className="border border-[#2a2a2a] p-1 text-neutral-400 hover:border-[#00f0ff] hover:text-[#00f0ff]"
            title="Refresh"
          >
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button
            data-testid="shift-log-download"
            onClick={download}
            className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 mono text-[10px] uppercase tracking-widest text-neutral-300 hover:border-[#39ff14] hover:text-[#39ff14]"
          >
            <Download className="h-3 w-3" /> CSV
          </button>
          {isAdmin && (
            <button
              data-testid="shift-log-clear"
              onClick={clear}
              className="border border-[#2a2a2a] p-1 text-neutral-400 hover:border-[#ff3b30] hover:text-[#ff3b30]"
              title="Clear log"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-[#2a2a2a] p-2">
        <Filter className="h-3 w-3 text-neutral-500" />
        {FILTERS.map((f) => (
          <button
            key={f.key || "all"}
            data-testid={`shift-log-filter-${f.key || "all"}`}
            onClick={() => setFilter(f.key)}
            className={`border px-2 py-0.5 mono text-[10px] uppercase tracking-widest transition-colors ${
              filter === f.key
                ? "border-[#00f0ff] bg-[#001a1f] text-[#00f0ff]"
                : "border-[#2a2a2a] text-neutral-400 hover:text-neutral-100"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto mono text-[11px]" data-testid="shift-log-list">
        {entries.length === 0 && !loading && (
          <div className="p-6 text-center text-neutral-600">
            // no events yet
          </div>
        )}
        {entries.map((e) => {
          const meta = EVENT_LABEL[e.event_type] || {
            label: e.event_type.toUpperCase(),
            color: "#9ca3af",
            Icon: Clock,
          };
          const IconC = meta.Icon;
          return (
            <div
              key={e.id}
              data-testid={`shift-log-entry-${e.id}`}
              className="grid grid-cols-[68px_58px_1fr] items-start gap-2 border-b border-[#1a1a1a] px-2 py-1.5"
            >
              <span className="text-neutral-500">
                {e.ts ? format(new Date(e.ts), "HH:mm:ss") : "—"}
              </span>
              <span
                className="flex items-center gap-1 text-[10px] uppercase tracking-widest"
                style={{ color: meta.color }}
              >
                <IconC className="h-3 w-3" />
                {meta.label}
              </span>
              <span className="text-neutral-200 break-words">{e.summary}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
