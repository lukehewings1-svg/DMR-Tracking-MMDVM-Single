import { useMemo, useState } from "react";
import { Map as MapIcon, MessageSquare, Clock, Users, Radio as RadioIcon } from "lucide-react";
import { MapView } from "@/components/MapView";
import { Roster } from "@/components/Roster";
import { GroupsPanel } from "@/components/GroupsPanel";
import { MessagingPanel } from "@/components/MessagingPanel";
import { ShiftLogPanel } from "@/components/ShiftLogPanel";
import { AlertsPanel } from "@/components/GeofencePanel";
import { RadioDetailModal } from "@/components/RadioDetailModal";
import { ScreenShell } from "@/components/ScreenShell";
import { TxNowList } from "@/components/TxNowList";
import { useLiveData } from "@/hooks/useLiveData";
import { useOverlays } from "@/hooks/useOverlays";
import { useBreakpoint, isNarrow } from "@/hooks/useBreakpoint";
import { useAuth } from "@/context/AuthContext";

function Tab({ active, onClick, icon, label, testid }) {
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className={`flex flex-1 items-center justify-center gap-1.5 border-r border-[#2a2a2a] px-2 py-1.5 mono text-[10px] uppercase tracking-widest last:border-r-0 transition-colors ${
        active ? "bg-[#001a1f] text-[#00f0ff]" : "text-neutral-400 hover:bg-[#111] hover:text-neutral-100"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

export default function DispatchPage() {
  const live = useLiveData();
  const { user } = useAuth();
  const { radios, groups, messages, voiceActivity, geofences, alerts } = live;
  const [overlays] = useOverlays(live.lastOverlayEvent);
  const narrow = isNarrow(useBreakpoint());
  const [groupFilter, setGroupFilter] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [rightTab, setRightTab] = useState("msg");
  const [mobileView, setMobileView] = useState("map");

  const txActiveIds = useMemo(() => new Set((voiceActivity || []).map((v) => v.src_id)), [voiceActivity]);
  const filtered = groupFilter ? radios.filter((r) => r.group_id === groupFilter) : radios;
  const open = (id) => {
    setSelectedId(id);
    setDetailId(id);
  };

  const map = (
    <MapView radios={filtered} groups={groups} selectedId={selectedId} txActiveIds={txActiveIds} onSelect={open} geofences={geofences} overlays={overlays} autoFit={!selectedId} />
  );
  const roster = (
    <Roster radios={filtered} groups={groups} selectedId={selectedId} txActiveIds={txActiveIds} onSelect={setSelectedId} onOpenDetail={open} consumeFlash={live.consumeFlash} />
  );
  const groupsBlock = (
    <div className="flex min-h-0 flex-col gap-2 overflow-y-auto p-2">
      <GroupsPanel groups={groups} filter={groupFilter} onFilter={setGroupFilter} onChanged={live.refreshAll} embedded />
      <TxNowList voiceActivity={voiceActivity} groups={groups} radios={radios} />
      <AlertsPanel alerts={alerts} onClear={live.clearAllAlerts} embedded />
    </div>
  );
  const messaging = <MessagingPanel radios={radios} groups={groups} messages={messages} currentUser={user} />;
  const log = <ShiftLogPanel liveEntry={live.liveLogEntry} />;

  return (
    <ScreenShell live={live} testid="dispatch-page" title="Dispatch" onEmergencyFocus={open}>
      {narrow ? (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-hidden">
            {mobileView === "map" && map}
            {mobileView === "radios" && <div className="flex h-full min-h-0 flex-col">{roster}</div>}
            {mobileView === "groups" && groupsBlock}
            {mobileView === "msg" && <div className="flex h-full min-h-0 flex-col">{messaging}</div>}
            {mobileView === "log" && <div className="flex h-full min-h-0 flex-col">{log}</div>}
          </div>
          <nav className="flex shrink-0 border-t border-[#2a2a2a] bg-[#0a0a0a]">
            <Tab testid="dtab-map" active={mobileView === "map"} onClick={() => setMobileView("map")} icon={<MapIcon className="h-3.5 w-3.5" />} label="Map" />
            <Tab testid="dtab-radios" active={mobileView === "radios"} onClick={() => setMobileView("radios")} icon={<RadioIcon className="h-3.5 w-3.5" />} label="Radios" />
            <Tab testid="dtab-groups" active={mobileView === "groups"} onClick={() => setMobileView("groups")} icon={<Users className="h-3.5 w-3.5" />} label="Groups" />
            <Tab testid="dtab-msg" active={mobileView === "msg"} onClick={() => setMobileView("msg")} icon={<MessageSquare className="h-3.5 w-3.5" />} label="Msg" />
            <Tab testid="dtab-log" active={mobileView === "log"} onClick={() => setMobileView("log")} icon={<Clock className="h-3.5 w-3.5" />} label="Log" />
          </nav>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[280px_minmax(0,1fr)_380px]">
          <div data-testid="dispatch-roster" className="flex min-h-0 flex-col border-r border-[#2a2a2a] bg-[#0a0a0a]">{roster}</div>
          <div className="grid min-h-0 grid-rows-[minmax(0,1fr)_260px]">
            <div data-testid="dispatch-map" className="relative min-h-0">{map}</div>
            <div data-testid="dispatch-groups" className="min-h-0 border-t border-[#2a2a2a] bg-[#0a0a0a]">{groupsBlock}</div>
          </div>
          <div className="flex min-h-0 flex-col border-l border-[#2a2a2a] bg-[#0a0a0a]">
            <div className="flex shrink-0 border-b border-[#2a2a2a]">
              <Tab testid="dispatch-tab-msg" active={rightTab === "msg"} onClick={() => setRightTab("msg")} icon={<MessageSquare className="h-3 w-3" />} label="Messages" />
              <Tab testid="dispatch-tab-log" active={rightTab === "log"} onClick={() => setRightTab("log")} icon={<Clock className="h-3 w-3" />} label="Shift log" />
            </div>
            <div className="flex min-h-0 flex-1 flex-col">{rightTab === "msg" ? messaging : log}</div>
          </div>
        </div>
      )}
      <RadioDetailModal
        dmrId={detailId}
        radio={radios.find((r) => r.dmr_id === detailId)}
        groups={groups}
        messages={messages}
        onClose={() => {
          setDetailId(null);
          setSelectedId(null);
        }}
        onSaved={live.refreshAll}
        onDeleted={() => {
          setDetailId(null);
          live.refreshAll();
        }}
      />
    </ScreenShell>
  );
}
