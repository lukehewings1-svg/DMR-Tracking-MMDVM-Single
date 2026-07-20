import { AlertOctagon, X } from "lucide-react";
import { clearEmergency } from "@/lib/api";
import { formatDistanceToNowStrict } from "date-fns";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

export function EmergencyBanner({ emergencies, onFocus, onCleared }) {
  const { user } = useAuth();
  // Regular users can also acknowledge emergencies when the org allows it —
  // the backend enforces the actual policy (org.user_can_ack_emergency), the
  // UI just shows the button and surfaces the error on failure if disabled.
  const isAdmin = user?.role === "admin" || user?.role === "super_admin";
  if (!emergencies || emergencies.length === 0) return null;

  const handleClear = async (id) => {
    try {
      await clearEmergency(id);
      toast.success("Emergency cleared");
      onCleared?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to clear");
    }
  };

  return (
    <div
      data-testid="emergency-banner"
      className="border-b-2 border-[#ff3b30] bg-[#1a0505] px-4 py-2"
      style={{ animation: "emergency-pulse 1s ease-in-out infinite" }}
    >
      <div className="flex items-center gap-3">
        <AlertOctagon
          className="h-6 w-6 shrink-0 text-[#ff3b30]"
          style={{ animation: "emergency-icon 0.6s ease-in-out infinite alternate" }}
        />
        <div className="flex-1 overflow-x-auto">
          <div className="mono flex items-center gap-4 text-[11px]">
            <span className="font-bold uppercase tracking-[0.35em] text-[#ff3b30]">
              EMERGENCY · {emergencies.length} ACTIVE
            </span>
            {emergencies.slice(0, 6).map((e) => (
              <button
                key={e.id}
                data-testid={`emergency-chip-${e.id}`}
                onClick={() => onFocus?.(e.dmr_id)}
                className="flex items-center gap-1.5 border border-[#ff3b30]/60 bg-black px-2 py-0.5 text-neutral-100 hover:bg-[#ff3b30] hover:text-black"
              >
                <span className="font-semibold">{e.callsign || `ID ${e.dmr_id}`}</span>
                <span className="text-neutral-500">
                  {e.timestamp
                    ? formatDistanceToNowStrict(new Date(e.timestamp))
                    : ""}
                </span>
                {isAdmin && (
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={(ev) => {
                      ev.stopPropagation();
                      handleClear(e.id);
                    }}
                    data-testid={`emergency-clear-${e.id}`}
                    className="ml-1 rounded-none border border-transparent p-0.5 hover:border-current"
                    title="Acknowledge / clear"
                  >
                    <X className="h-3 w-3" />
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
