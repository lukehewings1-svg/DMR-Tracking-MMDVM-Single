import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { TopBar } from "@/components/TopBar";
import { MapView } from "@/components/MapView";
import { Roster } from "@/components/Roster";
import { PacketLog } from "@/components/PacketLog";
import { Injector } from "@/components/Injector";
import { ParserStatus } from "@/components/ParserStatus";
import { RadioDetailModal } from "@/components/RadioDetailModal";
import { GeofencePanel, AlertsPanel } from "@/components/GeofencePanel";
import { GroupsPanel } from "@/components/GroupsPanel";
import { ChannelFilter } from "@/components/ChannelFilter";
import { RepeaterConfigPanel } from "@/components/RepeaterConfigPanel";
import { MessagingPanel } from "@/components/MessagingPanel";
import { RepeatersPanel } from "@/components/RepeatersPanel";
import { EmergencyBanner } from "@/components/EmergencyBanner";
import { ShiftLogPanel } from "@/components/ShiftLogPanel";
import { useLiveData } from "@/hooks/useLiveData";
import { useAuth } from "@/context/AuthContext";
import { clearAll } from "@/lib/api";
import { toast } from "sonner";
import { LogOut, ShieldCheck, Trash2, BookOpen, MessageSquare, Map as MapIcon, Clock } from "lucide-react";

export default function Dashboard() {
  const { user, signOut } = useAuth();
  const {
    radios,
    packets,
    status,
    geofences,
    alerts,
    groups,
    channels,
    messages,
    repeaters,
    emergencies,
    voiceActivity,
    liveLogEntry,
    connected,
    lastEventAt,
    refreshAll,
    clearAllAlerts,
    consumeFlash,
  } = useLiveData();

  const [selectedId, setSelectedId] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [groupFilter, setGroupFilter] = useState(null);
  const [channelFilter, setChannelFilter] = useState(null);
  const [rightTab, setRightTab] = useState("ops"); // ops | msg

  const isAdmin = user?.role === "admin";

  const filteredRadios = useMemo(() => {
    let result = radios;
    if (groupFilter) result = result.filter((r) => r.group_id === groupFilter);
    if (channelFilter)
      result = result.filter((r) => (r.last_channel || 1) === channelFilter);
    return result;
  }, [radios, groupFilter, channelFilter]);
  const detailRadio = radios.find((r) => r.dmr_id === detailId);

  const openDetail = (id) => setDetailId(id);
  const focus = (id) => setSelectedId(id);

  const handleClear = async () => {
    if (!window.confirm("Clear all radios and history?")) return;
    await clearAll();
    toast.success("Cleared");
    refreshAll();
  };

  return (
    <div
      className="grid h-screen w-screen grid-rows-[auto_auto_auto_1fr] overflow-hidden bg-[#050505]"
      data-testid="dashboard"
    >
      <TopBar status={status} connected={connected} lastEventAt={lastEventAt} />

      {/* Session strip */}
      <div className="flex items-center justify-between border-b border-[#2a2a2a] bg-[#0a0a0a] px-4 py-1.5 mono text-[11px]">
        <div className="flex items-center gap-3">
          <span className="text-neutral-500">OPERATOR</span>
          <span className="text-neutral-100">{user?.email}</span>
          <span
            className={`border px-1.5 py-0.5 text-[9px] uppercase tracking-widest ${
              isAdmin ? "border-[#00f0ff] text-[#00f0ff]" : "border-[#2a2a2a] text-neutral-400"
            }`}
          >
            {user?.role}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Link
            data-testid="nav-setup-guide"
            to="/setup"
            className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 text-neutral-300 hover:border-[#00f0ff] hover:text-[#00f0ff]"
          >
            <BookOpen className="h-3 w-3" /> Setup Guide
          </Link>
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

      <EmergencyBanner
        emergencies={emergencies}
        onFocus={(id) => {
          focus(id);
          openDetail(id);
        }}
        onCleared={refreshAll}
      />

      <div className="grid min-h-0 grid-cols-[300px_1fr_340px]">
        <Roster
          radios={filteredRadios}
          selectedId={selectedId}
          onSelect={focus}
          onOpenDetail={openDetail}
          consumeFlash={consumeFlash}
          groups={groups}
        />

        <div className="grid min-h-0 grid-rows-[1fr_240px]">
          <MapView
            radios={filteredRadios}
            groups={groups}
            selectedId={selectedId}
            onSelect={(id) => {
              focus(id);
              openDetail(id);
            }}
            geofences={geofences}
          />
          <PacketLog packets={packets} />
        </div>

        <div className="flex flex-col border-l border-[#2a2a2a] bg-[#0a0a0a] min-h-0">
          {/* Right column tabs */}
          <div className="flex border-b border-[#2a2a2a] shrink-0">
            <TabBtn
              testid="tab-ops"
              active={rightTab === "ops"}
              onClick={() => setRightTab("ops")}
              icon={<MapIcon className="h-3 w-3" />}
              label="Ops"
            />
            <TabBtn
              testid="tab-messages"
              active={rightTab === "msg"}
              onClick={() => setRightTab("msg")}
              icon={<MessageSquare className="h-3 w-3" />}
              label={`Messages${messages.length ? ` (${messages.length})` : ""}`}
            />
            <TabBtn
              testid="tab-shift-log"
              active={rightTab === "log"}
              onClick={() => setRightTab("log")}
              icon={<Clock className="h-3 w-3" />}
              label="Log"
            />
          </div>

          {rightTab === "ops" ? (
            <div className="flex-1 overflow-y-auto">
              <ChannelFilter
                channels={channels}
                filter={channelFilter}
                onFilter={setChannelFilter}
                onChanged={refreshAll}
              />
              <RepeaterConfigPanel channels={channels} />
              <GroupsPanel
                groups={groups}
                filter={groupFilter}
                onFilter={setGroupFilter}
                onChanged={refreshAll}
              />
              <RepeatersPanel repeaters={repeaters} voiceActivity={voiceActivity} />
              <ParserStatus packets={packets} parsers={status?.parsers} />
              <AlertsPanel alerts={alerts} onClear={clearAllAlerts} />
              <GeofencePanel onChange={refreshAll} />
              <Injector onSent={refreshAll} />
            </div>
          ) : rightTab === "msg" ? (
            <MessagingPanel
              radios={radios}
              groups={groups}
              messages={messages}
              currentUser={user}
            />
          ) : (
            <ShiftLogPanel liveEntry={liveLogEntry} />
          )}
        </div>
      </div>

      <RadioDetailModal
        dmrId={detailId}
        radio={detailRadio}
        groups={groups}
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

function TabBtn({ active, onClick, icon, label, testid }) {
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className={`flex flex-1 items-center justify-center gap-1.5 border-r border-[#2a2a2a] py-1.5 mono text-[10px] uppercase tracking-widest last:border-r-0 transition-colors ${
        active
          ? "bg-[#001a1f] text-[#00f0ff]"
          : "text-neutral-400 hover:bg-[#111] hover:text-neutral-100"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
