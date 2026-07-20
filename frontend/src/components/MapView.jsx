import { useEffect, useMemo, useRef } from "react";
import {
  MapContainer,
  Marker,
  Polyline,
  Circle,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet-rotate";
import ReactDOMServer from "react-dom/server";
import { useQuery } from "@tanstack/react-query";
import { fetchPositions } from "@/lib/api";
import { iconFor } from "@/lib/icons";
import { BaseLayers } from "@/components/BaseLayers";
import { RotateControl } from "@/components/RotateControl";

function buildIcon(radio, selected, groupColor, tx) {
  const label = radio.callsign || `ID ${radio.dmr_id}`;
  const ageSec = radio.last_seen
    ? (Date.now() - new Date(radio.last_seen).getTime()) / 1000
    : 999;
  const stale = ageSec > 90;
  const distress = radio.in_emergency;
  const color =
    (distress && "#ff3b30") ||
    (tx && "#39ff14") ||
    (stale && "#ffb800") ||
    (selected && "#00f0ff") ||
    groupColor ||
    radio.color ||
    "#39ff14";
  const IconComp = iconFor(radio.icon);
  const iconSvg = ReactDOMServer.renderToStaticMarkup(
    <IconComp size={16} color={color} strokeWidth={2.25} />
  );

  let ringExtra = "";
  if (distress) {
    ringExtra = `animation: emergency-ring 0.9s ease-in-out infinite alternate;`;
  } else if (tx) {
    ringExtra = `animation: emergency-ring 0.6s ease-in-out infinite alternate;`;
  }
  const boxShadow =
    distress
      ? `0 0 18px ${color}`
      : tx
      ? `0 0 22px ${color}, 0 0 10px ${color}`
      : `0 0 8px ${color}55`;
  const txDot = tx
    ? `<span style="position:absolute;left:-4px;top:-4px;width:10px;height:10px;background:#39ff14;box-shadow:0 0 8px #39ff14;border:1px solid #050505;animation:emergency-ring 0.5s ease-in-out infinite alternate;"></span>`
    : "";
  const suffix = distress ? " · SOS" : tx ? " · TX" : "";
  const html = `
<div class="radio-marker ${stale ? "stale" : ""} ${selected ? "selected" : ""} ${distress ? "distress" : ""} ${tx ? "tx-active" : ""}" style="width:28px;height:28px;">
  <span class="ring" style="border-color:${color};inset:0;${ringExtra}"></span>
  <span class="ico" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(5,5,5,0.85);border:1px solid ${color};box-shadow:${boxShadow};">
    ${iconSvg}
  </span>
  ${txDot}
  <span class="label" style="left:32px;top:4px;color:${color};border-color:${color}55;">
    ${escapeHtml(label)}${suffix}
  </span>
</div>`;

  return L.divIcon({
    className: "",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    html,
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
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

function PanTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (!target) return;
    map.setView(target, Math.max(map.getZoom(), 12), { animate: true });
  }, [target, map]);
  return null;
}

function MapReadyEmitter({ onMapReady }) {
  const map = useMap();
  useEffect(() => {
    onMapReady?.(map);
  }, [map, onMapReady]);
  return null;
}

function TrailPolyline({ dmrId, color }) {
  const { data } = useQuery({
    queryKey: ["positions", dmrId],
    queryFn: () => fetchPositions(dmrId),
    refetchInterval: 8000,
    enabled: !!dmrId,
  });
  const points = useMemo(() => (data || []).map((p) => [p.lat, p.lon]), [data]);
  if (points.length < 2) return null;
  return (
    <Polyline
      positions={points}
      pathOptions={{ color, weight: 2, opacity: 0.85, dashArray: "4 4" }}
    />
  );
}

import { OverlayLayer, OverlayLayerBoundsSync } from "@/components/OverlayLayer";
import { OverlayEditor } from "@/components/OverlayEditor";
import { OverlayImageCorners } from "@/components/OverlayImageCorners";

export function MapView({
  radios,
  selectedId,
  onSelect,
  geofences = [],
  groups = [],
  overlays = [],
  overlaysVisible = true,
  editingOverlay = null,
  canEditOverlays = false,
  onMapReady,
  txActiveIds,
}) {
  const groupById = new Map(groups.map((g) => [g.id, g]));
  const txSet = txActiveIds || new Set();
  const withPos = radios.filter((r) => r.last_lat != null && r.last_lon != null);
  const center = withPos[0]
    ? [withPos[0].last_lat, withPos[0].last_lon]
    : [39.5, -98.35];
  const selected = withPos.find((r) => r.dmr_id === selectedId);
  const panTarget = selected && [selected.last_lat, selected.last_lon];

  // Overlays: while an admin is editing a set, the OverlayEditor owns those
  // shapes visually. So we render *other* active sets via OverlayLayer, but
  // exclude the one being edited to avoid a double render.
  const visibleActive = overlaysVisible
    ? overlays.filter((o) => o.active)
    : [];
  const overlaysForLayer = editingOverlay
    ? visibleActive.filter((o) => o.id !== editingOverlay.id)
    : visibleActive;

  return (
    <div className="relative h-full w-full" data-testid="map-view">
      <MapContainer
        center={center}
        zoom={4}
        className="h-full w-full"
        preferCanvas
        zoomControl
        attributionControl
        rotate
        rotateControl={false}
        bearing={0}
        touchRotate
        shiftKeyRotate
      >
        <MapReadyEmitter onMapReady={onMapReady} />
        <BaseLayers defaultLayer="Dark" />
        <RotateControl />
        <FitToRadios radios={withPos} />
        <PanTo target={panTarget} />

        {/* Event overlays (shapes + images) */}
        <OverlayLayerBoundsSync overlays={[...overlaysForLayer, editingOverlay].filter(Boolean)} />
        {/* image overlays for the set being edited are still rendered normally;
            the editor only owns the *shape* layers */}
        {editingOverlay && overlaysVisible && (
          <OverlayLayer overlays={[{ ...editingOverlay, shapes: [] }]} />
        )}
        <OverlayLayer overlays={overlaysForLayer} />
        <OverlayEditor overlay={editingOverlay} canEdit={canEditOverlays && !!editingOverlay} />
        {canEditOverlays && editingOverlay && (
          <OverlayImageCorners overlay={editingOverlay} />
        )}

        {geofences.map((f) => (
          <Circle
            key={f.id}
            center={[f.lat, f.lon]}
            radius={f.radius_m}
            pathOptions={{
              color: "#ffb800",
              weight: 1,
              opacity: 0.6,
              fillColor: "#ffb800",
              fillOpacity: 0.06,
              dashArray: "2 4",
            }}
          />
        ))}

        {withPos.map((r) => {
          const g = r.group_id ? groupById.get(r.group_id) : null;
          const color = g?.color || r.color || "#39ff14";
          return (
            <TrailPolyline
              key={`trail-${r.dmr_id}`}
              dmrId={r.dmr_id}
              color={r.in_emergency ? "#ff3b30" : r.dmr_id === selectedId ? "#00f0ff" : color}
            />
          );
        })}
        {withPos.map((r) => {
          const g = r.group_id ? groupById.get(r.group_id) : null;
          const color = g?.color || r.color || "#39ff14";
          const tx = txSet.has(r.dmr_id);
          return (
            <Marker
              key={`m-${r.dmr_id}-${r.icon || "Radio"}-${color}-${r.in_emergency ? "e" : "n"}-${tx ? "tx" : "rx"}`}
              position={[r.last_lat, r.last_lon]}
              icon={buildIcon(r, r.dmr_id === selectedId, color, tx)}
              eventHandlers={{ click: () => onSelect?.(r.dmr_id) }}
            />
          );
        })}
      </MapContainer>
      <div className="pointer-events-none absolute bottom-2 left-2 border border-[#2a2a2a] bg-black/70 px-2 py-1 mono text-[10px] text-neutral-400">
        OSM · CARTO DARK · {withPos.length} contact
        {withPos.length === 1 ? "" : "s"}
        {geofences.length > 0 ? ` · ${geofences.length} fence${geofences.length === 1 ? "" : "s"}` : ""}
        {visibleActive.length > 0
          ? ` · ${visibleActive.length} overlay${visibleActive.length === 1 ? "" : "s"}`
          : ""}
      </div>
    </div>
  );
}
