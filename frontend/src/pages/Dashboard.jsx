import { useEffect, useMemo, useState } from "react";
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
import { OverlayManagerPanel } from "@/components/OverlayManagerPanel";
import { CollapsiblePanel, usePersistedState } from "@/components/CollapsiblePanel";
import { useLiveData } from "@/hooks/useLiveData";
import { useBreakpoint, isNarrow } from "@/hooks/useBreakpoint";
import { useAuth } from "@/context/AuthContext";
import { clearAll, listOverlays } from "@/lib/api";
import { toast } from "sonner";
import {
  LogOut,
  ShieldCheck,
  Trash2,
  BookOpen,
  MessageSquare,
  Map as MapIcon,
  Clock,
  Layers,
  Menu,
  X,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  PanelBottomClose,
  PanelBottomOpen,
  Radio as RadioIcon,
  MoreHorizontal,
  Filter,
  Users,
  Antenna,
  Cpu,
  Bell,
  ShieldAlert,
  FlaskConical,
} from "lucide-react";

export default function Dashboard() {
  const { user, signOut } = useAuth();
  const bp = useBreakpoint();
  const narrow = isNarrow(bp);

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
    lastOverlayEvent,
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
  const [rightTab, setRightTab] = useState("ops"); // ops | msg | log
  const [mobileView, setMobileView] = useState("map"); // map | roster | ops | msg | log | menu
  const [overlays, setOverlays] = useState([]);
  const [editingOverlayId, setEditingOverlayId] = useState(null);
  const [overlaysVisible, setOverlaysVisible] = useState(true);
  const [mapInstance, setMapInstance] = useState(null);

  // Desktop panel collapse state (persisted)
  const [leftOpen, setLeftOpen] = usePersistedState("panel:dash:leftOpen", true);
  const [rightOpen, setRightOpen] = usePersistedState("panel:dash:rightOpen", true);
  const [bottomOpen, setBottomOpen] = usePersistedState("panel:dash:bottomOpen", true);

  // Mobile menu
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const refreshOverlays = async () => {
    try {
      const data = await listOverlays();
      setOverlays(data);
    } catch {
      /* noop */
    }
  };

  useEffect(() => {
    refreshOverlays();
  }, []);

  useEffect(() => {
    if (!lastOverlayEvent) return;
    refreshOverlays();
  }, [lastOverlayEvent]);

  const editingOverlay = overlays.find((o) => o.id === editingOverlayId) || null;
  const isAdmin = user?.role === "admin" || user?.role === "super_admin";
  const isSuperAdmin = user?.role === "super_admin";

  // Set of DMR IDs currently transmitting voice — powers the map + roster
  // "live TX" pulse.
  const txActiveIds = useMemo(
    () => new Set((voiceActivity || []).map((v) => v.src_id).filter(Boolean)),
    [voiceActivity]
  );

  // Command-centre mode: pin the messages panel as a persistent side column
  // in addition to (not instead of) the Ops/Log tabs. Auto-on for TVs (>=1920)
  // but user can toggle it any time. Persisted.
  const [pinMessages, setPinMessages] = usePersistedState(
    "panel:dash:pinMessages",
    false,
  );
  const showMessagesSideColumn = !narrow && pinMessages;

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

  const activeOverlayCount = overlays.filter((o) => o.active).length;
  const emergencyCount = emergencies?.length || 0;

  // ------------------------------------------------------------ Sub-panels
  const OpsPanels = (
    <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
      {isAdmin && (
        <OverlayManagerPanel
          editingOverlayId={editingOverlayId}
          onEditOverlay={setEditingOverlayId}
          currentMap={mapInstance}
          onOverlaysChanged={setOverlays}
        />
      )}
      <CollapsiblePanel
        id="channels"
        title="Channels (timeslots)"
        icon={<Filter className="h-3 w-3" />}
        testid="panel-channels"
      >
        <ChannelFilter
          channels={channels}
          filter={channelFilter}
          onFilter={setChannelFilter}
          onChanged={refreshAll}
          embedded
        />
      </CollapsiblePanel>
      {isAdmin && (
        <CollapsiblePanel
          id="repeater-config"
          title="MMDVM Channel Bindings"
          icon={<Cpu className="h-3 w-3" />}
          testid="panel-repeater-config"
          defaultOpen={false}
        >
          <RepeaterConfigPanel channels={channels} embedded />
        </CollapsiblePanel>
      )}
      <CollapsiblePanel
        id="groups"
        title="Groups (talkgroups)"
        icon={<Users className="h-3 w-3" />}
        testid="panel-groups"
      >
        <GroupsPanel
          groups={groups}
          filter={groupFilter}
          onFilter={setGroupFilter}
          onChanged={refreshAll}
          embedded
        />
      </CollapsiblePanel>
      <CollapsiblePanel
        id="repeaters"
        title="Connected MMDVMs"
        icon={<Antenna className="h-3 w-3" />}
        testid="panel-repeaters"
        defaultOpen={false}
      >
        <RepeatersPanel repeaters={repeaters} voiceActivity={voiceActivity} embedded />
      </CollapsiblePanel>
      <CollapsiblePanel
        id="parsers"
        title="Parsers"
        icon={<Cpu className="h-3 w-3" />}
        testid="panel-parsers"
        defaultOpen={false}
      >
        <ParserStatus packets={packets} parsers={status?.parsers} embedded />
      </CollapsiblePanel>
      <CollapsiblePanel
        id="alerts"
        title="Alerts"
        icon={<Bell className="h-3 w-3" />}
        testid="panel-alerts"
      >
        <AlertsPanel alerts={alerts} onClear={clearAllAlerts} embedded />
      </CollapsiblePanel>
      <CollapsiblePanel
        id="geofences"
        title="Geofences"
        icon={<ShieldAlert className="h-3 w-3" />}
        testid="panel-geofences"
        defaultOpen={false}
      >
        <GeofencePanel onChange={refreshAll} embedded />
      </CollapsiblePanel>
      {isAdmin && (
        <CollapsiblePanel
          id="injector"
          title="Injector (testing)"
          icon={<FlaskConical className="h-3 w-3" />}
          testid="panel-injector"
          defaultOpen={false}
        >
          <Injector onSent={refreshAll} embedded />
        </CollapsiblePanel>
      )}
    </div>
  );

  const RightColumnTabs = (
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
        label={
          messages.length
            ? `Msg\u2009${messages.length > 99 ? "99+" : messages.length}`
            : "Msg"
        }
      />
      <TabBtn
        testid="tab-shift-log"
        active={rightTab === "log"}
        onClick={() => setRightTab("log")}
        icon={<Clock className="h-3 w-3" />}
        label="Log"
      />
    </div>
  );

  const RightColumnBody =
    rightTab === "ops" ? (
      OpsPanels
    ) : rightTab === "msg" ? (
      <MessagingPanel
        radios={radios}
        groups={groups}
        messages={messages}
        currentUser={user}
      />
    ) : (
      <ShiftLogPanel liveEntry={liveLogEntry} />
    );

  const RosterPanel = (
    <Roster
      radios={filteredRadios}
      selectedId={selectedId}
      txActiveIds={txActiveIds}
      onSelect={(id) => {
        focus(id);
        if (narrow) setMobileView("map");
      }}
      onOpenDetail={(id) => {
        openDetail(id);
        if (narrow) setMobileView("map");
      }}
      consumeFlash={consumeFlash}
      groups={groups}
    />
  );

  // ------------------------------------------------------------ Layouts
  const NarrowLayout = (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-hidden">
        {mobileView === "map" && (
          <div className="grid h-full min-h-0 grid-rows-[1fr_auto]">
            <MapView
              radios={filteredRadios}
              groups={groups}
              selectedId={selectedId}
              txActiveIds={txActiveIds}
              onSelect={(id) => {
                focus(id);
                openDetail(id);
              }}
              geofences={geofences}
              overlays={overlays}
              overlaysVisible={overlaysVisible}
              editingOverlay={editingOverlay}
              canEditOverlays={isAdmin}
              onMapReady={setMapInstance}
            />
            {bottomOpen && <PacketLog packets={packets} />}
          </div>
        )}
        {mobileView === "roster" && (
          <div className="flex h-full min-h-0 flex-col">{RosterPanel}</div>
        )}
        {mobileView === "ops" && (
          <div className="flex h-full min-h-0 flex-col bg-[#0a0a0a]">
            {OpsPanels}
          </div>
        )}
        {mobileView === "msg" && (
          <div className="flex h-full min-h-0 flex-col bg-[#0a0a0a]">
            <MessagingPanel
              radios={radios}
              groups={groups}
              messages={messages}
              currentUser={user}
            />
          </div>
        )}
        {mobileView === "log" && (
          <div className="flex h-full min-h-0 flex-col bg-[#0a0a0a]">
            <ShiftLogPanel liveEntry={liveLogEntry} />
          </div>
        )}
      </div>
      <nav
        data-testid="mobile-tabbar"
        className="grid shrink-0 grid-cols-5 border-t border-[#2a2a2a] bg-[#050505]"
      >
        <MobileTab
          testid="mtab-map"
          icon={<MapIcon className="h-4 w-4" />}
          label="Map"
          badge={activeOverlayCount || null}
          active={mobileView === "map"}
          onClick={() => setMobileView("map")}
        />
        <MobileTab
          testid="mtab-roster"
          icon={<RadioIcon className="h-4 w-4" />}
          label="Radios"
          badge={filteredRadios.length}
          active={mobileView === "roster"}
          onClick={() => setMobileView("roster")}
        />
        <MobileTab
          testid="mtab-ops"
          icon={<Filter className="h-4 w-4" />}
          label="Ops"
          active={mobileView === "ops"}
          onClick={() => setMobileView("ops")}
        />
        <MobileTab
          testid="mtab-msg"
          icon={<MessageSquare className="h-4 w-4" />}
          label="Msg"
          badge={messages.length || null}
          active={mobileView === "msg"}
          onClick={() => setMobileView("msg")}
        />
        <MobileTab
          testid="mtab-log"
          icon={<Clock className="h-4 w-4" />}
          label="Log"
          active={mobileView === "log"}
          onClick={() => setMobileView("log")}
        />
      </nav>
    </div>
  );

  const DesktopLayout = (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      {/* Left column */}
      {leftOpen ? (
        <div
          data-testid="left-column"
          className="flex w-[300px] shrink-0 flex-col border-r border-[#2a2a2a] bg-[#0a0a0a] min-h-0"
        >
          <div className="flex items-center justify-between border-b border-[#2a2a2a] px-2 py-1">
            <span className="mono text-[9px] uppercase tracking-[0.3em] text-neutral-500">
              Roster
            </span>
            <button
              data-testid="collapse-left"
              onClick={() => setLeftOpen(false)}
              className="border border-transparent p-1 text-neutral-500 hover:border-[#2a2a2a] hover:text-neutral-100"
              title="Minimise roster"
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex min-h-0 flex-1">{RosterPanel}</div>
        </div>
      ) : (
        <button
          data-testid="expand-left"
          onClick={() => setLeftOpen(true)}
          className="flex w-8 shrink-0 flex-col items-center justify-start gap-2 border-r border-[#2a2a2a] bg-[#0a0a0a] py-3 text-neutral-500 hover:text-[#00f0ff]"
          title="Show roster"
        >
          <PanelLeftOpen className="h-4 w-4" />
          <span
            className="mono text-[9px] uppercase tracking-[0.3em]"
            style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
          >
            Roster · {filteredRadios.length}
          </span>
        </button>
      )}

      {/* Center column */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="relative min-h-0 flex-1">
          <MapView
            radios={filteredRadios}
            groups={groups}
            selectedId={selectedId}
            txActiveIds={txActiveIds}
            onSelect={(id) => {
              focus(id);
              openDetail(id);
            }}
            geofences={geofences}
            overlays={overlays}
            overlaysVisible={overlaysVisible}
            editingOverlay={editingOverlay}
            canEditOverlays={isAdmin}
            onMapReady={setMapInstance}
          />
        </div>
        {bottomOpen ? (
          <div className="grid h-[240px] shrink-0 grid-rows-[auto_1fr] border-t border-[#2a2a2a] bg-black">
            <div className="flex items-center justify-between border-b border-[#2a2a2a] px-3 py-1">
              <span className="mono text-[9px] uppercase tracking-[0.3em] text-neutral-500">
                Raw Packet Log
              </span>
              <button
                data-testid="collapse-bottom"
                onClick={() => setBottomOpen(false)}
                className="border border-transparent p-1 text-neutral-500 hover:border-[#2a2a2a] hover:text-neutral-100"
                title="Minimise packet log"
              >
                <PanelBottomClose className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="min-h-0">
              <PacketLog packets={packets} embedded />
            </div>
          </div>
        ) : (
          <button
            data-testid="expand-bottom"
            onClick={() => setBottomOpen(true)}
            className="flex h-7 shrink-0 items-center justify-center gap-2 border-t border-[#2a2a2a] bg-[#0a0a0a] text-neutral-500 hover:text-[#00f0ff]"
            title="Show packet log"
          >
            <PanelBottomOpen className="h-3.5 w-3.5" />
            <span className="mono text-[9px] uppercase tracking-[0.3em]">
              Raw Packet Log · {packets.length}
            </span>
          </button>
        )}
      </div>

      {/* Pinned messages side column (command-centre mode) */}
      {showMessagesSideColumn && (
        <div
          data-testid="side-messages-column"
          className="flex w-[340px] shrink-0 flex-col border-l border-[#2a2a2a] bg-[#0a0a0a] min-h-0"
        >
          <div className="flex items-center justify-between border-b border-[#2a2a2a] px-2 py-1">
            <span className="mono text-[9px] uppercase tracking-[0.3em] text-[#00f0ff]">
              Messages
            </span>
            <button
              data-testid="unpin-side-messages"
              onClick={() => setPinMessages(false)}
              className="border border-transparent p-1 text-neutral-500 hover:border-[#2a2a2a] hover:text-neutral-100"
              title="Unpin messages"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex min-h-0 flex-1">
            <MessagingPanel
              radios={radios}
              groups={groups}
              messages={messages}
              currentUser={user}
            />
          </div>
        </div>
      )}

      {/* Right column */}
      {rightOpen ? (
        <div
          data-testid="right-column"
          className="flex w-[340px] shrink-0 flex-col border-l border-[#2a2a2a] bg-[#0a0a0a] min-h-0"
        >
          <div className="flex items-center border-b border-[#2a2a2a]">
            <div className="flex flex-1 shrink-0">{RightColumnTabs}</div>
            <button
              data-testid="collapse-right"
              onClick={() => setRightOpen(false)}
              className="border-l border-[#2a2a2a] p-1.5 text-neutral-500 hover:text-neutral-100"
              title="Minimise right panel"
            >
              <PanelRightClose className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col">{RightColumnBody}</div>
        </div>
      ) : (
        <button
          data-testid="expand-right"
          onClick={() => setRightOpen(true)}
          className="flex w-8 shrink-0 flex-col items-center justify-start gap-2 border-l border-[#2a2a2a] bg-[#0a0a0a] py-3 text-neutral-500 hover:text-[#00f0ff]"
          title="Show ops / messages / log"
        >
          <PanelRightOpen className="h-4 w-4" />
          <span
            className="mono text-[9px] uppercase tracking-[0.3em]"
            style={{ writingMode: "vertical-rl" }}
          >
            Ops · Msg · Log
          </span>
        </button>
      )}
    </div>
  );

  const SessionActions = (
    <>
      <button
        data-testid="toggle-pin-messages"
        onClick={() => setPinMessages((v) => !v)}
        title={pinMessages ? "Unpin messages column" : "Pin messages as a side column"}
        className={`items-center gap-1 border px-2 py-1 mono text-[11px] uppercase tracking-widest ${
          narrow ? "hidden" : "flex"
        } ${
          pinMessages
            ? "border-[#00f0ff] text-[#00f0ff]"
            : "border-[#2a2a2a] text-neutral-500 hover:text-neutral-300"
        }`}
      >
        <MessageSquare className="h-3 w-3" />
        Msg:&nbsp;{pinMessages ? "Pinned" : "Tab"}
      </button>
      <button
        data-testid="toggle-overlays"
        onClick={() => setOverlaysVisible((v) => !v)}
        title={overlaysVisible ? "Hide overlays" : "Show overlays"}
        className={`flex items-center gap-1 border px-2 py-1 mono text-[11px] uppercase tracking-widest ${
          overlaysVisible
            ? "border-[#00f0ff] text-[#00f0ff]"
            : "border-[#2a2a2a] text-neutral-500 hover:text-neutral-300"
        }`}
      >
        <Layers className="h-3 w-3" />
        <span className="hidden sm:inline">Overlays:&nbsp;</span>
        {overlaysVisible ? "On" : "Off"}
        {activeOverlayCount > 0 && overlaysVisible && (
          <span className="ml-1 text-[9px] text-[#00f0ff]">· {activeOverlayCount}</span>
        )}
      </button>
      <Link
        data-testid="nav-setup-guide"
        to="/setup"
        className={`items-center gap-1 border border-[#2a2a2a] px-2 py-1 text-neutral-300 hover:border-[#00f0ff] hover:text-[#00f0ff] ${
          narrow ? "hidden" : "flex"
        }`}
      >
        <BookOpen className="h-3 w-3" /> Setup Guide
      </Link>
      {isAdmin && (
        <>
          <Link
            data-testid="nav-admin"
            to="/admin/users"
            className={`items-center gap-1 border border-[#2a2a2a] px-2 py-1 text-neutral-300 hover:border-[#00f0ff] hover:text-[#00f0ff] ${
              narrow ? "hidden" : "flex"
            }`}
          >
            <ShieldCheck className="h-3 w-3" /> Users
          </Link>
          {isSuperAdmin && (
            <Link
              data-testid="nav-orgs"
              to="/admin/orgs"
              className={`items-center gap-1 border border-[#00f0ff]/40 px-2 py-1 text-[#00f0ff] hover:border-[#00f0ff] ${
                narrow ? "hidden" : "flex"
              }`}
            >
              <ShieldCheck className="h-3 w-3" /> Orgs
            </Link>
          )}
          <button
            data-testid="nav-clear"
            onClick={handleClear}
            className={`items-center gap-1 border border-[#2a2a2a] px-2 py-1 text-neutral-300 hover:border-[#ff3b30] hover:text-[#ff3b30] ${
              narrow ? "hidden" : "flex"
            }`}
          >
            <Trash2 className="h-3 w-3" /> Clear All
          </button>
        </>
      )}
      <button
        data-testid="nav-signout"
        onClick={signOut}
        className={`items-center gap-1 border border-[#2a2a2a] px-2 py-1 text-neutral-300 hover:border-[#ff3b30] hover:text-[#ff3b30] ${
          narrow ? "hidden" : "flex"
        }`}
      >
        <LogOut className="h-3 w-3" /> Sign out
      </button>
      {/* Mobile menu button */}
      <button
        data-testid="mobile-menu"
        onClick={() => setMobileMenuOpen(true)}
        className={`items-center gap-1 border border-[#2a2a2a] px-2 py-1 text-neutral-300 hover:border-[#00f0ff] hover:text-[#00f0ff] ${
          narrow ? "flex" : "hidden"
        }`}
        title="More"
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>
    </>
  );

  return (
    <div
      data-testid="dashboard"
      data-breakpoint={bp}
      className="flex h-screen w-screen flex-col overflow-hidden bg-[#050505]"
    >
      <TopBar status={status} connected={connected} lastEventAt={lastEventAt} user={user} />

      {/* Session strip */}
      <div className="flex items-center justify-between gap-2 border-b border-[#2a2a2a] bg-[#0a0a0a] px-2 py-1.5 mono text-[11px] md:px-4">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <span className="hidden text-neutral-500 md:inline">OPERATOR</span>
          <span className="truncate text-neutral-100">{user?.email}</span>
          <span
            className={`shrink-0 border px-1.5 py-0.5 text-[9px] uppercase tracking-widest ${
              isAdmin ? "border-[#00f0ff] text-[#00f0ff]" : "border-[#2a2a2a] text-neutral-400"
            }`}
          >
            {user?.role}
          </span>
          {emergencyCount > 0 && (
            <span className="shrink-0 border border-[#ff3b30] px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-[#ff3b30]">
              {emergencyCount} SOS
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1 sm:gap-2">{SessionActions}</div>
      </div>

      <EmergencyBanner
        emergencies={emergencies}
        onFocus={(id) => {
          focus(id);
          openDetail(id);
          if (narrow) setMobileView("map");
        }}
        onCleared={refreshAll}
      />

      {narrow ? NarrowLayout : DesktopLayout}

      {/* Mobile "More" menu drawer */}
      {mobileMenuOpen && narrow && (
        <div
          className="fixed inset-0 z-[900] bg-black/70"
          onClick={() => setMobileMenuOpen(false)}
          data-testid="mobile-menu-drawer"
        >
          <div
            className="absolute right-0 top-0 flex h-full w-64 max-w-[85vw] flex-col gap-1 border-l border-[#2a2a2a] bg-[#0a0a0a] p-3"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setMobileMenuOpen(false)}
              className="mb-2 self-end border border-[#2a2a2a] p-1 text-neutral-400 hover:border-[#00f0ff] hover:text-[#00f0ff]"
            >
              <X className="h-4 w-4" />
            </button>
            <Link
              to="/setup"
              onClick={() => setMobileMenuOpen(false)}
              className="flex items-center gap-2 border border-[#2a2a2a] px-3 py-2 text-neutral-100 hover:border-[#00f0ff] hover:text-[#00f0ff]"
            >
              <BookOpen className="h-4 w-4" /> Setup Guide
            </Link>
            {isAdmin && (
              <>
                <Link
                  to="/admin/users"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex items-center gap-2 border border-[#2a2a2a] px-3 py-2 text-neutral-100 hover:border-[#00f0ff] hover:text-[#00f0ff]"
                >
                  <ShieldCheck className="h-4 w-4" /> Users
                </Link>
                {isSuperAdmin && (
                  <Link
                    to="/admin/orgs"
                    onClick={() => setMobileMenuOpen(false)}
                    className="flex items-center gap-2 border border-[#00f0ff]/40 px-3 py-2 text-[#00f0ff] hover:border-[#00f0ff]"
                  >
                    <ShieldCheck className="h-4 w-4" /> Organizations
                  </Link>
                )}
                <button
                  onClick={() => {
                    setMobileMenuOpen(false);
                    handleClear();
                  }}
                  className="flex items-center gap-2 border border-[#2a2a2a] px-3 py-2 text-left text-neutral-100 hover:border-[#ff3b30] hover:text-[#ff3b30]"
                >
                  <Trash2 className="h-4 w-4" /> Clear All
                </button>
              </>
            )}
            <button
              onClick={() => {
                setMobileMenuOpen(false);
                signOut();
              }}
              className="flex items-center gap-2 border border-[#2a2a2a] px-3 py-2 text-left text-neutral-100 hover:border-[#ff3b30] hover:text-[#ff3b30]"
            >
              <LogOut className="h-4 w-4" /> Sign out
            </button>
          </div>
        </div>
      )}

      <RadioDetailModal
        dmrId={detailId}
        radio={detailRadio}
        groups={groups}
        messages={messages}
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
      className={`flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap border-r border-[#2a2a2a] px-1.5 py-1.5 mono text-[10px] uppercase tracking-widest last:border-r-0 transition-colors ${
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

function MobileTab({ icon, label, badge, active, onClick, testid }) {
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className={`relative flex flex-col items-center justify-center gap-0.5 py-1.5 mono text-[9px] uppercase tracking-widest transition-colors ${
        active ? "text-[#00f0ff]" : "text-neutral-400 hover:text-neutral-100"
      }`}
    >
      {icon}
      <span>{label}</span>
      {badge != null && badge > 0 && (
        <span
          className={`absolute right-3 top-1 rounded-full px-1 mono text-[8px] ${
            active ? "bg-[#00f0ff] text-black" : "bg-[#2a2a2a] text-neutral-300"
          }`}
        >
          {badge > 99 ? "99+" : badge}
        </span>
      )}
      {active && (
        <span className="absolute inset-x-3 top-0 h-0.5 bg-[#00f0ff]" />
      )}
    </button>
  );
}
