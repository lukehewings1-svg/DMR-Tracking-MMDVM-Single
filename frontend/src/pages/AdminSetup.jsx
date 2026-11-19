import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Filter, Cpu, Users, Antenna, Bell, ShieldAlert, FlaskConical, ShieldCheck, BookOpen, Trash2, ScrollText, Download } from "lucide-react";
import { MapView } from "@/components/MapView";
import { ScreenShell } from "@/components/ScreenShell";
import { CollapsiblePanel } from "@/components/CollapsiblePanel";
import { OverlayManagerPanel } from "@/components/OverlayManagerPanel";
import { ChannelFilter } from "@/components/ChannelFilter";
import { RepeaterConfigPanel } from "@/components/RepeaterConfigPanel";
import { GroupsPanel } from "@/components/GroupsPanel";
import { RepeatersPanel } from "@/components/RepeatersPanel";
import { ParserStatus } from "@/components/ParserStatus";
import { GeofencePanel, AlertsPanel } from "@/components/GeofencePanel";
import { Injector } from "@/components/Injector";
import { PacketLog } from "@/components/PacketLog";
import { UpdatePanel } from "@/components/UpdatePanel";
import { useLiveData } from "@/hooks/useLiveData";
import { useOverlays } from "@/hooks/useOverlays";
import { clearAll } from "@/lib/api";

const linkCls = "flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 text-neutral-300 hover:border-[#00f0ff] hover:text-[#00f0ff]";

export default function AdminSetup() {
  const live = useLiveData();
  const { radios, groups, channels, geofences, alerts, packets, repeaters, voiceActivity, status } = live;
  const [overlays, setOverlays] = useOverlays(live.lastOverlayEvent);
  const [editingOverlayId, setEditingOverlayId] = useState(null);
  const [mapInstance, setMapInstance] = useState(null);
  const [channelFilter, setChannelFilter] = useState(null);
  const editingOverlay = overlays.find((o) => o.id === editingOverlayId) || null;

  const handleClear = async () => {
    if (!window.confirm("Clear all radios and history?")) return;
    await clearAll();
    toast.success("Cleared");
    live.refreshAll();
  };

  const actions = (
    <>
      <Link data-testid="admin-nav-users" to="/admin/users" className={linkCls}>
        <ShieldCheck className="h-3 w-3" /> <span className="hidden sm:inline">Users &amp; access</span>
      </Link>
      <Link data-testid="admin-nav-setup" to="/setup" className={linkCls}>
        <BookOpen className="h-3 w-3" /> <span className="hidden sm:inline">Setup guide</span>
      </Link>
      <button data-testid="admin-clear-all" onClick={handleClear} className={`${linkCls} hover:border-[#ff3b30] hover:text-[#ff3b30]`}>
        <Trash2 className="h-3 w-3" /> <span className="hidden sm:inline">Clear all</span>
      </button>
    </>
  );

  return (
    <ScreenShell live={live} testid="admin-setup-page" title="Admin setup" actions={actions}>
      <div className="flex min-h-0 flex-1 flex-col lg:grid lg:grid-cols-[420px_minmax(0,1fr)]">
        <div data-testid="admin-panels" className="min-h-0 overflow-y-auto border-r border-[#2a2a2a] bg-[#0a0a0a] max-lg:max-h-[55vh]">
          <CollapsiblePanel id="adm-update" title="Software update" icon={<Download className="h-3 w-3" />} testid="admin-panel-update">
            <UpdatePanel />
          </CollapsiblePanel>
          <OverlayManagerPanel editingOverlayId={editingOverlayId} onEditOverlay={setEditingOverlayId} currentMap={mapInstance} onOverlaysChanged={setOverlays} />
          <CollapsiblePanel id="adm-channels" title="Channels (timeslots)" icon={<Filter className="h-3 w-3" />} testid="admin-panel-channels">
            <ChannelFilter channels={channels} filter={channelFilter} onFilter={setChannelFilter} onChanged={live.refreshAll} embedded />
          </CollapsiblePanel>
          <CollapsiblePanel id="adm-bindings" title="MMDVM Channel Bindings" icon={<Cpu className="h-3 w-3" />} testid="admin-panel-bindings">
            <RepeaterConfigPanel channels={channels} embedded />
          </CollapsiblePanel>
          <CollapsiblePanel id="adm-groups" title="Groups (talkgroups)" icon={<Users className="h-3 w-3" />} testid="admin-panel-groups">
            <GroupsPanel groups={groups} filter={null} onFilter={() => {}} onChanged={live.refreshAll} embedded />
          </CollapsiblePanel>
          <CollapsiblePanel id="adm-mmdvms" title="Connected MMDVMs" icon={<Antenna className="h-3 w-3" />} testid="admin-panel-mmdvms">
            <RepeatersPanel repeaters={repeaters} voiceActivity={voiceActivity} embedded />
          </CollapsiblePanel>
          <CollapsiblePanel id="adm-geofences" title="Geofences" icon={<ShieldAlert className="h-3 w-3" />} testid="admin-panel-geofences">
            <GeofencePanel onChange={live.refreshAll} embedded />
          </CollapsiblePanel>
          <CollapsiblePanel id="adm-alerts" title="Alerts" icon={<Bell className="h-3 w-3" />} testid="admin-panel-alerts" defaultOpen={false}>
            <AlertsPanel alerts={alerts} onClear={live.clearAllAlerts} embedded />
          </CollapsiblePanel>
          <CollapsiblePanel id="adm-parsers" title="Parsers" icon={<Cpu className="h-3 w-3" />} testid="admin-panel-parsers" defaultOpen={false}>
            <ParserStatus packets={packets} parsers={status?.parsers} embedded />
          </CollapsiblePanel>
          <CollapsiblePanel id="adm-injector" title="Injector (testing)" icon={<FlaskConical className="h-3 w-3" />} testid="admin-panel-injector" defaultOpen={false}>
            <Injector onSent={live.refreshAll} embedded />
          </CollapsiblePanel>
          <CollapsiblePanel id="adm-packets" title="Raw packet log" icon={<ScrollText className="h-3 w-3" />} testid="admin-panel-packets" defaultOpen={false}>
            <div className="h-[260px]">
              <PacketLog packets={packets} embedded />
            </div>
          </CollapsiblePanel>
        </div>
        <div data-testid="admin-map" className="relative min-h-[320px] flex-1">
          <MapView
            radios={radios}
            groups={groups}
            geofences={geofences}
            overlays={overlays}
            editingOverlay={editingOverlay}
            canEditOverlays
            onMapReady={setMapInstance}
          />
        </div>
      </div>
    </ScreenShell>
  );
}
