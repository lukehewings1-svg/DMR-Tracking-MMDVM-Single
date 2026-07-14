import { useEffect, useMemo, useRef } from "react";
import {
  Circle,
  ImageOverlay,
  Marker,
  Polygon,
  Polyline,
  Rectangle,
  Tooltip,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import ReactDOMServer from "react-dom/server";
import { MapPin } from "lucide-react";
import { uploadUrl } from "@/lib/api";

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function markerIcon(color, label) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    <MapPin size={20} color={color} strokeWidth={2.25} fill="#050505" />
  );
  const html = `
<div class="overlay-marker" style="position:relative;width:24px;height:24px;filter:drop-shadow(0 0 4px ${color}88);">
  <div style="position:absolute;left:12px;top:-2px;transform:translate(0,-100%);white-space:nowrap;
              color:${color};background:rgba(5,5,5,0.85);border:1px solid ${color};
              padding:1px 5px;font:600 10px 'JetBrains Mono',monospace;letter-spacing:0.05em;">
    ${escapeHtml(label)}
  </div>
  <div style="position:absolute;left:2px;top:2px;">${svg}</div>
</div>`;
  return L.divIcon({ className: "", iconSize: [24, 24], iconAnchor: [12, 22], html });
}

function ShapeLabel({ name, description, color }) {
  if (!name && !description) return null;
  return (
    <Tooltip direction="top" opacity={0.95} sticky>
      <div className="mono text-[11px]">
        {name && (
          <div style={{ color }} className="font-bold">
            {name}
          </div>
        )}
        {description && (
          <div className="mt-0.5 text-neutral-300">{description}</div>
        )}
      </div>
    </Tooltip>
  );
}

function ShapeRenderer({ shape, editable, onSelect }) {
  const g = shape.geometry || {};
  const color = shape.color || "#00f0ff";
  const style = {
    color,
    weight: 2,
    opacity: 0.9,
    fillColor: color,
    fillOpacity: 0.15,
  };
  const eventHandlers = editable && onSelect ? { click: () => onSelect(shape) } : undefined;
  const idAttr = { "data-shape-id": shape.id };

  if (shape.type === "marker" && g.lat != null && g.lng != null) {
    return (
      <Marker
        position={[g.lat, g.lng]}
        icon={markerIcon(color, shape.name || "Marker")}
        eventHandlers={eventHandlers}
        {...idAttr}
      >
        <ShapeLabel
          name={shape.name}
          description={shape.description}
          color={color}
        />
      </Marker>
    );
  }
  if (shape.type === "circle" && g.center && g.radius != null) {
    return (
      <Circle
        center={g.center}
        radius={g.radius}
        pathOptions={style}
        eventHandlers={eventHandlers}
      >
        <ShapeLabel {...shape} color={color} />
      </Circle>
    );
  }
  if (shape.type === "polyline" && Array.isArray(g.latlngs)) {
    return (
      <Polyline
        positions={g.latlngs}
        pathOptions={{ ...style, dashArray: "5 5", fillOpacity: 0 }}
        eventHandlers={eventHandlers}
      >
        <ShapeLabel {...shape} color={color} />
      </Polyline>
    );
  }
  if (shape.type === "polygon" && Array.isArray(g.latlngs)) {
    return (
      <Polygon
        positions={g.latlngs}
        pathOptions={style}
        eventHandlers={eventHandlers}
      >
        <ShapeLabel {...shape} color={color} />
      </Polygon>
    );
  }
  if (shape.type === "rectangle" && Array.isArray(g.bounds)) {
    return (
      <Rectangle
        bounds={g.bounds}
        pathOptions={style}
        eventHandlers={eventHandlers}
      >
        <ShapeLabel {...shape} color={color} />
      </Rectangle>
    );
  }
  return null;
}

/**
 * Renders all shapes and image overlays for a list of overlay sets.
 * Purely presentational — editing lives in <OverlayEditor/>.
 */
export function OverlayLayer({ overlays, onSelectShape }) {
  const flat = useMemo(() => overlays || [], [overlays]);
  return (
    <>
      {flat.map((ov) =>
        (ov.images || []).map((img) => (
          <ImageOverlay
            key={`img-${ov.id}-${img.id}`}
            url={uploadUrl(img.url)}
            bounds={img.bounds}
            opacity={img.opacity ?? 0.6}
            interactive={false}
          />
        ))
      )}
      {flat.map((ov) =>
        (ov.shapes || []).map((s) => (
          <ShapeRenderer
            key={`s-${ov.id}-${s.id}`}
            shape={s}
            editable={!!onSelectShape}
            onSelect={onSelectShape}
          />
        ))
      )}
    </>
  );
}

/**
 * A tiny presence helper that forces Leaflet to invalidate size when the
 * overlay set changes — otherwise brand-new image overlays sometimes render at
 * the wrong bounds until the next zoom event.
 */
export function OverlayLayerBoundsSync({ overlays }) {
  const map = useMap();
  const prev = useRef(0);
  useEffect(() => {
    const count = (overlays || []).reduce(
      (sum, o) => sum + (o.images?.length || 0) + (o.shapes?.length || 0),
      0
    );
    if (count !== prev.current) {
      prev.current = count;
      setTimeout(() => map.invalidateSize(), 60);
    }
  }, [overlays, map]);
  return null;
}
