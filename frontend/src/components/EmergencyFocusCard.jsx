import { AlertOctagon } from "lucide-react";
import { formatDistanceToNowStrict } from "date-fns";

function Row({ label, value, testid }) {
  if (value == null || value === "") return null;
  return (
    <div className="grid grid-cols-[90px_1fr] gap-2">
      <span className="text-[9px] uppercase tracking-[0.25em] text-neutral-500">{label}</span>
      <span data-testid={testid} className="whitespace-pre-wrap break-words text-neutral-100">{value}</span>
    </div>
  );
}

export function EmergencyFocusCard({ emergency, radio, group, others, onPick }) {
  const r = radio || {};
  const lat = r.last_lat ?? emergency.last_lat;
  const lon = r.last_lon ?? emergency.last_lon;
  return (
    <div
      data-testid="emergency-focus-card"
      className="w-[min(380px,calc(100vw-24px))] border-2 border-[#ff3b30] bg-[#140303]/95 mono text-[12px] shadow-[0_0_30px_#ff3b3066] backdrop-blur"
    >
      <div className="flex items-center gap-2 bg-[#ff3b30] px-3 py-1.5 text-black">
        <AlertOctagon className="h-5 w-5" style={{ animation: "emergency-icon 0.6s ease-in-out infinite alternate" }} />
        <span className="font-bold uppercase tracking-[0.3em]">Emergency</span>
        <span className="ml-auto text-[10px] uppercase">
          {emergency.timestamp ? `${formatDistanceToNowStrict(new Date(emergency.timestamp))} ago` : ""}
        </span>
      </div>
      <div className="space-y-1.5 px-3 py-2">
        <div data-testid="emergency-focus-callsign" className="text-2xl font-bold text-[#ff3b30]">
          {r.callsign || emergency.callsign || `ID ${emergency.dmr_id}`}
        </div>
        <Row label="DMR ID" value={String(emergency.dmr_id)} testid="emergency-focus-dmrid" />
        <Row label="Group" value={group?.name} testid="emergency-focus-group" />
        <Row label="Crew" value={r.crew} testid="emergency-focus-crew" />
        <Row label="Notes" value={r.notes} testid="emergency-focus-notes" />
        <Row label="Position" value={lat != null ? `${lat.toFixed(5)}, ${lon.toFixed(5)}` : "no fix yet"} testid="emergency-focus-position" />
        <Row label="Speed" value={r.last_speed != null ? `${Math.round(r.last_speed)} km/h` : null} />
        <Row label="Last fix" value={r.last_seen ? `${formatDistanceToNowStrict(new Date(r.last_seen))} ago` : null} />
      </div>
      {others.length > 1 && (
        <div className="flex flex-wrap gap-1 border-t border-[#ff3b30]/40 px-3 py-2">
          {others.map((e) => (
            <button
              key={e.id}
              data-testid={`emergency-focus-pick-${e.dmr_id}`}
              onClick={() => onPick(e.id)}
              className={`border px-2 py-0.5 text-[10px] uppercase ${
                e.id === emergency.id ? "border-[#ff3b30] bg-[#ff3b30] text-black" : "border-[#ff3b30]/60 text-neutral-200 hover:bg-[#ff3b30]/20"
              }`}
            >
              {e.callsign || `ID ${e.dmr_id}`}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
