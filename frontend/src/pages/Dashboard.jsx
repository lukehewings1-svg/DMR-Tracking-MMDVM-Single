import { useState } from "react";
import { Link } from "react-router-dom";
import { TopBar } from "@/components/TopBar";
import { MapView } from "@/components/MapView";
import { Roster } from "@/components/Roster";
import { PacketLog } from "@/components/PacketLog";
import { Injector } from "@/components/Injector";
import { ParserStatus } from "@/components/ParserStatus";
import { RadioDetailModal } from "@/components/RadioDetailModal";
import { GeofencePanel, AlertsPanel } from "@/components/GeofencePanel";
import { useLiveData } from "@/hooks/useLiveData";
import { useAuth } from "@/context/AuthContext";
import { clearAll } from "@/lib/api";
import { toast } from "sonner";
import { LogOut, ShieldCheck, Trash2 } from "lucide-react";

export default function Dashboard() {
  const { user, signOut } = useAuth();
  const {
    radios,
    packets,
    status,
    geofences,
    alerts,
    connected,
    lastEventAt,
    refreshAll,
    clearAllAlerts,
    consumeFlash,
  } = useLiveData();
  const [selectedId, setSelectedId] = useState(null);
  const [detailId, setDetailId] = useState(null);

  const isAdmin = user?.role === "admin";
  const detailRadio = radios.find((r) => r.dmr_id === detailId);

  const openDetail = (id) => setDetailId(id);
  const focus = (id) => setSelectedId(id);

  const handleClear = async () => {
    if (!isAdmin) return;
    if (!window.confirm("Clear all radios and history?")) return;
    await clearAll();
    toast.success("Cleared");
    refreshAll();
  };

  return (
    <div
      className="grid h-screen w-screen grid-rows-[auto_auto_1fr] overflow-hidden bg-[#050505]"
      data-testid="dashboard"
    >
      <TopBar
        status={status}
        connected={connected}
        lastEventAt={lastEventAt}
      />

      {/* Session strip */}
      <div className="flex items-center justify-between border-b border-[#2a2a2a] bg-[#0a0a0a] px-4 py-1.5 mono text-[11px]">
        <div className="flex items-center gap-3">
          <span className="text-neutral-500">OPERATOR</span>
          <span className="text-neutral-100">{user?.email}</span>
          <span
            className={`border px-1.5 py-0.5 text-[9px] uppercase tracking-widest ${
              isAdmin
                ? "border-[#00f0ff] text-[#00f0ff]"
                : "border-[#2a2a2a] text-neutral-400"
            }`}
          >
            {user?.role}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {isAdmin && (
            <>
              <Link
                data-testid="nav-admin"
                to="/admin/users"
                className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 text-neutral-300 hover:border-[#00f0ff] hover:text-[#00f0ff]"
              >
                <ShieldCheck className="h-3 w-3" /> Users
              </Link>
              <button
                data-testid="nav-clear"
                onClick={handleClear}
                className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 text-neutral-300 hover:border-[#ff3b30] hover:text-[#ff3b30]"
              >
                <Trash2 className="h-3 w-3" /> Clear All
              </button>
            </>
          )}
          <button
            data-testid="nav-signout"
            onClick={signOut}
            className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 text-neutral-300 hover:border-[#ff3b30] hover:text-[#ff3b30]"
          >
            <LogOut className="h-3 w-3" /> Sign out
          </button>
        </div>
      </div>

      <div className="grid min-h-0 grid-cols-[300px_1fr_320px]">
        <Roster
          radios={radios}
          selectedId={selectedId}
          onSelect={focus}
          onOpenDetail={openDetail}
          consumeFlash={consumeFlash}
        />

        <div className="grid min-h-0 grid-rows-[1fr_240px]">
          <MapView
            radios={radios}
            selectedId={selectedId}
            onSelect={(id) => {
              focus(id);
              openDetail(id);
            }}
            geofences={geofences}
          />
          <PacketLog packets={packets} />
        </div>

        <div className="flex flex-col overflow-y-auto border-l border-[#2a2a2a] bg-[#0a0a0a]">
          <ParserStatus packets={packets} parsers={status?.parsers} />
          <AlertsPanel alerts={alerts} onClear={clearAllAlerts} />
          <GeofencePanel onChange={refreshAll} />
          <Injector onSent={refreshAll} />
          <ConnectionHelp status={status} />
        </div>
      </div>

      <RadioDetailModal
        dmrId={detailId}
        radio={detailRadio}
        onClose={() => setDetailId(null)}
        onSaved={refreshAll}
        onDeleted={() => {
          setDetailId(null);
          refreshAll();
        }}
      />
    </div>
  );
}

function ConnectionHelp({ status }) {
  const bind = status?.listener?.bind || "0.0.0.0:62031";
  const port = bind.split(":")[1] || "62031";
  return (
    <div data-testid="help-panel" className="p-3 text-[11px]">
      <div className="mb-1 text-[10px] uppercase tracking-[0.3em] text-neutral-500">
        MMDVM Setup
      </div>
      <ol className="mono space-y-1 text-neutral-400">
        <li>
          <span className="text-neutral-600">1.</span> In{" "}
          <span className="text-neutral-200">MMDVM.ini</span> under{" "}
          <span className="text-[#00f0ff]">[DMR Network]</span> set
          <br />
          <span className="pl-4 text-neutral-300">Address = {"<this host>"}</span>
          <br />
          <span className="pl-4 text-neutral-300">Port = {port}</span>
          <br />
          <span className="pl-4 text-neutral-300">Password = PASSWORD</span>
        </li>
        <li>
          <span className="text-neutral-600">2.</span> Restart MMDVMHost — it
          authenticates against this app as its HB master.
        </li>
        <li>
          <span className="text-neutral-600">3.</span> Enable GPS on your DMR
          radios. Positions decode via LRRP / Hytera / NMEA / APRS.
        </li>
      </ol>
      <div className="mt-3 border border-dashed border-[#2a2a2a] p-2 text-[10px] text-neutral-500">
        Note: in this hosted preview the UDP port is not publicly reachable.
        Self-host the backend to receive live MMDVM traffic, or use the injector
        above to see the pipeline end-to-end.
      </div>
    </div>
  );
}
