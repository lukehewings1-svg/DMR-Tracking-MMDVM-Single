import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  MapContainer,
  Marker,
  Circle,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import ReactDOMServer from "react-dom/server";
import {
  fetchSituationalSnapshot,
  situationalWsUrl,
} from "@/lib/api";
import { iconFor } from "@/lib/icons";
import { OverlayLayer } from "@/components/OverlayLayer";
import { BaseLayers } from "@/components/BaseLayers";
import { AlertOctagon, Radio as RadioIcon, ShieldAlert, Layers } from "lucide-react";

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function buildIcon(radio) {
  const label = radio.callsign || `ID ${radio.dmr_id}`;
  const ageSec = radio.last_seen
    ? (Date.now() - new Date(radio.last_seen).getTime()) / 1000
    : 999;
  const stale = ageSec > 90;
  const distress = radio.in_emergency;
  const color =
    (distress && "#ff3b30") ||
    (stale && "#ffb800") ||
    radio.color ||
    "#39ff14";
  const IconComp = iconFor(radio.icon);
  const iconSvg = ReactDOMServer.renderToStaticMarkup(
    <IconComp size={16} color={color} strokeWidth={2.25} />
  );
  const ringExtra = distress
    ? `animation: emergency-ring 0.9s ease-in-out infinite alternate;`
    : "";
  const boxShadow = distress ? `0 0 18px ${color}` : `0 0 8px ${color}55`;
  const html = `
<div class="radio-marker ${stale ? "stale" : ""} ${distress ? "distress" : ""}" style="width:28px;height:28px;">
  <span class="ring" style="border-color:${color};inset:0;${ringExtra}"></span>
  <span class="ico" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(5,5,5,0.85);border:1px solid ${color};box-shadow:${boxShadow};">
    ${iconSvg}
  </span>
  <span class="label" style="left:32px;top:4px;color:${color};border-color:${color}55;">
    ${escapeHtml(label)}${distress ? " · SOS" : ""}
  </span>
</div>`;
  return L.divIcon({ className: "", iconSize: [28, 28], iconAnchor: [14, 14], html });
}

function FitToRadios({ radios }) {
  const map = useMap();
  const didFitRef = useRef(false);
  useEffect(() => {
    if (didFitRef.current) return;
    const pts = radios
      .filter((r) => r.last_lat != null && r.last_lon != null)
      .map((r) => [r.last_lat, r.last_lon]);
    if (pts.length === 0) return;
    if (pts.length === 1) map.setView(pts[0], 13);
    else map.fitBounds(pts, { padding: [40, 40] });
    didFitRef.current = true;
  }, [radios, map]);
  return null;
}

export default function SituationalView() {
  const { token } = useParams();
  const [view, setView] = useState(null);
  const [radios, setRadios] = useState([]);
  const [emergencies, setEmergencies] = useState([]);
  const [overlays, setOverlays] = useState([]);
  const [overlaysVisible, setOverlaysVisible] = useState(true);
  const [error, setError] = useState(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

  const applyPosition = (radio) => {
    setRadios((prev) => {
      const idx = prev.findIndex((r) => r.dmr_id === radio.dmr_id);
      const merged = { ...(idx >= 0 ? prev[idx] : {}), ...radio };
      const next = idx >= 0 ? [...prev] : [merged, ...prev];
      if (idx >= 0) next[idx] = merged;
      next.sort((a, b) => (a.last_seen < b.last_seen ? 1 : -1));
      return next;
    });
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const snap = await fetchSituationalSnapshot(token);
        if (cancelled) return;
        setView(snap.view);
        setRadios(snap.radios || []);
        setEmergencies(snap.emergencies || []);
        setOverlays(snap.overlays || []);
      } catch (e) {
        if (!cancelled) setError(e?.response?.data?.detail || "Unknown or expired link.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    if (error) return;
    let cancelled = false;
    const connect = () => {
      if (cancelled) return;
      try {
        const ws = new WebSocket(situationalWsUrl(token));
        wsRef.current = ws;
        ws.onopen = () => setConnected(true);
        ws.onclose = () => {
          setConnected(false);
          if (!cancelled) setTimeout(connect, 3000);
        };
        ws.onmessage = (evt) => {
          try {
            const msg = JSON.parse(evt.data);
            if (msg.type === "position") applyPosition(msg.radio);
            else if (msg.type === "emergency") {
              setEmergencies((prev) => [msg.emergency, ...prev.filter((e) => e.id !== msg.emergency.id)]);
              setRadios((prev) =>
                prev.map((r) =>
                  r.dmr_id === msg.emergency.dmr_id ? { ...r, in_emergency: true } : r
                )
              );
            } else if (msg.type === "emergency_cleared") {
              setEmergencies((prev) => prev.filter((e) => e.id !== msg.emergency_id));
              setRadios((prev) =>
                prev.map((r) =>
                  r.dmr_id === msg.dmr_id ? { ...r, in_emergency: false } : r
                )
              );
            } else if (msg.type === "clear") {
              setRadios([]);
              setEmergencies([]);
              setOverlays([]);
            } else if (msg.type === "overlay_upserted") {
              setOverlays((prev) => {
                const idx = prev.findIndex((o) => o.id === msg.overlay.id);
                if (idx >= 0) {
                  const next = [...prev];
                  next[idx] = msg.overlay;
                  return next;
                }
                return [msg.overlay, ...prev];
              });
            } else if (msg.type === "overlay_removed") {
              setOverlays((prev) => prev.filter((o) => o.id !== msg.overlay_id));
            }
          } catch {
            /* noop */
          }
        };
      } catch {
        setTimeout(connect, 3000);
      }
    };
    connect();
    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, [token, error]);

  const withPos = useMemo(
    () => radios.filter((r) => r.last_lat != null && r.last_lon != null),
    [radios]
  );

  if (error) {
    return (
      <div
        className="flex h-screen items-center justify-center bg-[#050505] p-8"
        data-testid="situational-error"
      >
        <div className="max-w-md border border-[#ff3b30]/40 bg-[#1a0505] p-6 text-center">
          <ShieldAlert className="mx-auto mb-3 h-10 w-10 text-[#ff3b30]" />
          <div className="mono text-[10px] uppercase tracking-[0.35em] text-[#ff3b30]">
            access denied
          </div>
          <div className="mt-2 text-neutral-200">{error}</div>
          <div className="mt-4 mono text-[11px] text-neutral-500">
            Ask an admin for a new situational-awareness link.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen flex-col bg-[#050505]" data-testid="situational-view">
      <header className="flex items-center justify-between border-b border-[#2a2a2a] bg-[#0a0a0a] px-4 py-2 mono text-[11px]">
        <div className="flex items-center gap-3">
          <span className="text-[10px] uppercase tracking-[0.35em] text-[#00f0ff]">
            Situational awareness
          </span>
          <span
            className={`h-2 w-2 rounded-full ${
              connected ? "bg-[#39ff14]" : "bg-neutral-600"
            }`}
            title={connected ? "live" : "reconnecting…"}
          />
          {view && (
            <>
              <span className="text-neutral-500">·</span>
              <span className="text-neutral-100">{view.name}</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-4 text-neutral-400">
          <span className="flex items-center gap-1">
            <RadioIcon className="h-3 w-3" /> {withPos.length}
          </span>
          <span
            className={`flex items-center gap-1 ${
              emergencies.length > 0 ? "text-[#ff3b30]" : ""
            }`}
          >
            <AlertOctagon className="h-3 w-3" /> {emergencies.length}
          </span>
          {overlays.length > 0 && (
            <button
              data-testid="situational-toggle-overlays"
              onClick={() => setOverlaysVisible((v) => !v)}
              title={overlaysVisible ? "Hide overlays" : "Show overlays"}
              className={`flex items-center gap-1 border px-1.5 py-0.5 mono text-[10px] uppercase tracking-widest ${
                overlaysVisible
                  ? "border-[#00f0ff] text-[#00f0ff]"
                  : "border-[#2a2a2a] text-neutral-500 hover:text-neutral-300"
              }`}
            >
              <Layers className="h-3 w-3" /> {overlaysVisible ? "On" : "Off"}
              <span className="text-[9px] opacity-75">· {overlays.length}</span>
            </button>
          )}
          <span className="text-[10px] uppercase tracking-widest text-neutral-500">
            view only
          </span>
        </div>
      </header>

      {emergencies.length > 0 && (
        <div
          data-testid="situational-emergency-banner"
          className="border-b-2 border-[#ff3b30] bg-[#1a0505] px-4 py-2"
          style={{ animation: "emergency-pulse 1s ease-in-out infinite" }}
        />
      )}

      <div className="relative min-h-0 flex-1">
        <MapContainer
          center={[39.5, -98.35]}
          zoom={4}
          className="h-full w-full"
          preferCanvas
          zoomControl
        >
          <BaseLayers defaultLayer="Dark" />
          <FitToRadios radios={withPos} />
          {overlaysVisible && <OverlayLayer overlays={overlays} />}
          {withPos.map((r) => (
            <Marker
              key={`m-${r.dmr_id}-${r.icon || "Radio"}-${r.in_emergency ? "e" : "n"}`}
              position={[r.last_lat, r.last_lon]}
              icon={buildIcon(r)}
            />
          ))}
          {emergencies
            .filter((e) => e.last_lat != null && e.last_lon != null)
            .map((e) => (
              <Circle
                key={`sos-${e.id}`}
                center={[e.last_lat, e.last_lon]}
                radius={120}
                pathOptions={{
                  color: "#ff3b30",
                  weight: 2,
                  opacity: 0.9,
                  fillColor: "#ff3b30",
                  fillOpacity: 0.15,
                }}
              />
            ))}
        </MapContainer>

        <div className="pointer-events-none absolute bottom-2 left-2 z-[500] border border-[#2a2a2a] bg-black/70 px-2 py-1 mono text-[10px] text-neutral-400">
          READ-ONLY · OSM · CARTO DARK · {withPos.length} contact
          {withPos.length === 1 ? "" : "s"}
        </div>

        {emergencies.length > 0 && (
          <div
            className="pointer-events-none absolute right-4 top-4 z-[500] flex max-w-xs flex-col gap-2"
            data-testid="situational-emergency-list"
          >
            {emergencies.slice(0, 6).map((e) => (
              <div
                key={e.id}
                className="border-2 border-[#ff3b30] bg-black/90 px-3 py-1.5 mono text-[11px] text-neutral-100 shadow-[0_0_18px_rgba(255,59,48,0.5)]"
                style={{ animation: "emergency-pulse 1.2s ease-in-out infinite" }}
              >
                <span className="mr-2 font-bold text-[#ff3b30]">SOS</span>
                {e.callsign || `ID ${e.dmr_id}`}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
