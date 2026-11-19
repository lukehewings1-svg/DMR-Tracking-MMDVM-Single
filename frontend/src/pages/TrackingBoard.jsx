import { useEffect, useMemo, useState } from "react";
import { Maximize, Volume2 } from "lucide-react";
import { MapView } from "@/components/MapView";
import { ScreenNav } from "@/components/ScreenNav";
import { EmergencyBanner } from "@/components/EmergencyBanner";
import { EmergencyFocusCard } from "@/components/EmergencyFocusCard";
import { TxNowList } from "@/components/TxNowList";
import { BoardClock } from "@/components/BoardClock";
import { BoardGroupFilter, filterByGroups } from "@/components/BoardGroupFilter";
import { usePersistedState } from "@/components/CollapsiblePanel";
import { useLiveData } from "@/hooks/useLiveData";
import { useOverlays } from "@/hooks/useOverlays";

function useSoundArmed() {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (armed) return;
    const arm = () => setArmed(true);
    window.addEventListener("pointerdown", arm, { once: true });
    window.addEventListener("keydown", arm, { once: true });
    return () => {
      window.removeEventListener("pointerdown", arm);
      window.removeEventListener("keydown", arm);
    };
  }, [armed]);
  return armed;
}

export default function TrackingBoard() {
  const live = useLiveData();
  const { radios, groups, emergencies, voiceActivity, geofences } = live;
  const [overlays] = useOverlays(live.lastOverlayEvent);
  const [pickedId, setPickedId] = useState(null);
  const soundArmed = useSoundArmed();
  const [shownGroups, setShownGroups] = usePersistedState("board:groupIds", []);
  const shownRadios = filterByGroups(radios, shownGroups);
  // Emergencies always stay on the board, whatever talkgroups are shown.
  const boardRadios = [...shownRadios, ...radios.filter((r) => r.in_emergency && !shownRadios.includes(r))];
  const shownTgs = new Set(groups.filter((g) => shownGroups.includes(g.id)).map((g) => g.talkgroup_id));
  const shownVoice = shownGroups.length ? (voiceActivity || []).filter((v) => shownTgs.has(v.talkgroup_id)) : voiceActivity;

  const txActiveIds = useMemo(() => new Set((voiceActivity || []).map((v) => v.src_id)), [voiceActivity]);
  const withPos = shownRadios.filter((r) => r.last_lat != null);
  const emergency = emergencies.find((e) => e.id === pickedId) || emergencies[0] || null;
  const emgRadio = emergency ? radios.find((r) => r.dmr_id === emergency.dmr_id) : null;
  const emgGroup = groups.find((g) => g.id === (emgRadio?.group_id || emergency?.group_id));
  const focusLat = emgRadio?.last_lat ?? emergency?.last_lat;
  const focusLon = emgRadio?.last_lon ?? emergency?.last_lon;
  const focusTarget = emergency && focusLat != null ? [focusLat, focusLon] : null;

  const goFullscreen = () => document.documentElement.requestFullscreen?.().catch(() => {});

  return (
    <div data-testid="tracking-board" className="flex h-screen w-screen flex-col overflow-hidden bg-black">
      <div className="flex items-center justify-between gap-2 border-b border-[#2a2a2a] bg-[#050505] px-2 py-1 mono text-[11px]">
        <div className="flex min-w-0 items-center gap-3">
          <ScreenNav />
          <span className="hidden shrink-0 uppercase tracking-[0.35em] text-neutral-400 xl:inline">Tracking Board</span>
          <BoardGroupFilter groups={groups} selected={shownGroups} onChange={setShownGroups} />
        </div>
        <button
          data-testid="board-fullscreen"
          onClick={goFullscreen}
          className="flex shrink-0 items-center gap-1 border border-[#2a2a2a] px-2 py-1 uppercase tracking-widest text-neutral-300 hover:border-[#00f0ff] hover:text-[#00f0ff]"
        >
          <Maximize className="h-3 w-3" /> <span className="hidden sm:inline">Full screen</span>
        </button>
      </div>
      <EmergencyBanner emergencies={emergencies} onFocus={(id) => setPickedId(emergencies.find((e) => e.dmr_id === id)?.id)} onCleared={live.refreshAll} />

      <div className="relative min-h-0 flex-1">
        <MapView
          radios={boardRadios}
          groups={groups}
          txActiveIds={txActiveIds}
          geofences={geofences}
          overlays={overlays}
          autoFit
          focusTarget={focusTarget}
          showTrails={false}
        />
        <div className="pointer-events-none absolute right-14 top-3 z-[1000]">
          <BoardClock radioCount={withPos.length} connected={live.connected} />
        </div>
        <div className="absolute bottom-10 left-3 z-[1000] w-[min(300px,calc(100vw-24px))]">
          <TxNowList voiceActivity={shownVoice} groups={groups} radios={radios} />
        </div>
        {emergency && (
          <div className="absolute left-14 right-3 top-3 z-[1000] sm:right-auto">
            <EmergencyFocusCard emergency={emergency} radio={emgRadio} group={emgGroup} others={emergencies} onPick={setPickedId} />
          </div>
        )}
        {!soundArmed && (
          <div data-testid="board-sound-prompt" className="pointer-events-none absolute bottom-10 right-3 z-[1000] flex items-center gap-2 border border-[#ffb800] bg-black/85 px-3 py-2 mono text-[11px] text-[#ffb800]">
            <Volume2 className="h-4 w-4" /> Click anywhere once to enable the emergency siren
          </div>
        )}
      </div>
    </div>
  );
}
