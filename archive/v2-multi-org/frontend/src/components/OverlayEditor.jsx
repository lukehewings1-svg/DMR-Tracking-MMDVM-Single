import { useEffect, useMemo, useRef } from "react";
import { useMap } from "react-leaflet";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import L from "leaflet";
import { replaceOverlayShapes } from "@/lib/api";
import { toast } from "sonner";

/**
 * Serialises a Leaflet layer created by geoman into our overlay-shape schema.
 * Returns `null` if it's a layer type we don't persist (e.g. rotate handles).
 */
function serialiseLayer(layer) {
  const shapeId = layer._overlayShapeId || undefined;
  const opts = layer.options || {};
  const color = opts.color || "#00f0ff";
  const base = {
    id: shapeId,
    color,
    name: layer._overlayShapeName || "",
    description: layer._overlayShapeDescription || "",
  };
  if (layer instanceof L.Circle) {
    const c = layer.getLatLng();
    return {
      ...base,
      type: "circle",
      geometry: { center: [c.lat, c.lng], radius: layer.getRadius() },
    };
  }
  if (layer instanceof L.Rectangle) {
    const b = layer.getBounds();
    return {
      ...base,
      type: "rectangle",
      geometry: {
        bounds: [
          [b.getSouth(), b.getWest()],
          [b.getNorth(), b.getEast()],
        ],
      },
    };
  }
  if (layer instanceof L.Polygon) {
    const rings = layer.getLatLngs();
    const first = Array.isArray(rings[0]) ? rings[0] : rings;
    return {
      ...base,
      type: "polygon",
      geometry: { latlngs: first.map((p) => [p.lat, p.lng]) },
    };
  }
  if (layer instanceof L.Polyline) {
    const pts = layer.getLatLngs();
    return {
      ...base,
      type: "polyline",
      geometry: { latlngs: pts.map((p) => [p.lat, p.lng]) },
    };
  }
  if (layer instanceof L.Marker) {
    const c = layer.getLatLng();
    return {
      ...base,
      type: "marker",
      geometry: { lat: c.lat, lng: c.lng },
    };
  }
  return null;
}

/**
 * Sits inside a <MapContainer> and gives admins the geoman toolbox to draw
 * shapes into the *active* overlay set. Shapes are round-tripped through the
 * backend: we throw away the current geoman layers on every prop change and
 * rebuild them from `overlay.shapes` so this component is single-source-of-truth.
 */
export function OverlayEditor({ overlay, canEdit }) {
  const map = useMap();
  const groupRef = useRef(null);
  const overlayIdRef = useRef(null);
  const saveTimerRef = useRef(null);
  const pendingSaveRef = useRef(false);

  // pm toolbar toggle
  useEffect(() => {
    if (!map || !canEdit) return;
    map.pm.addControls({
      position: "topleft",
      drawMarker: true,
      drawCircleMarker: false,
      drawPolyline: true,
      drawRectangle: true,
      drawPolygon: true,
      drawCircle: true,
      drawText: false,
      editMode: true,
      dragMode: true,
      cutPolygon: false,
      removalMode: true,
      rotateMode: false,
    });
    map.pm.setPathOptions({ color: "#00f0ff", fillColor: "#00f0ff" });
    map.pm.setGlobalOptions({ snappable: true, snapDistance: 20 });
    return () => {
      try {
        map.pm.removeControls();
      } catch (e) {
        /* noop */
      }
    };
  }, [map, canEdit]);

  // hydrate + persist
  const shapesKey = useMemo(
    () => JSON.stringify(overlay?.shapes || []),
    [overlay?.shapes]
  );

  useEffect(() => {
    if (!map) return;
    if (!groupRef.current) {
      groupRef.current = L.featureGroup().addTo(map);
    }
    const group = groupRef.current;
    // If overlay changed (different id) or shape set changed, rebuild layers.
    // Suppress rebuild if a save is in flight (we don't want to flicker while
    // the server acknowledges our own edit).
    if (pendingSaveRef.current) {
      pendingSaveRef.current = false;
      return;
    }
    group.clearLayers();
    overlayIdRef.current = overlay?.id || null;
    if (!overlay) return;
    for (const s of overlay.shapes || []) {
      const g = s.geometry || {};
      const style = { color: s.color || "#00f0ff" };
      let layer = null;
      if (s.type === "marker" && g.lat != null && g.lng != null) {
        layer = L.marker([g.lat, g.lng]);
      } else if (s.type === "circle" && g.center && g.radius != null) {
        layer = L.circle(g.center, { ...style, radius: g.radius });
      } else if (s.type === "rectangle" && g.bounds) {
        layer = L.rectangle(g.bounds, style);
      } else if (s.type === "polygon" && g.latlngs) {
        layer = L.polygon(g.latlngs, style);
      } else if (s.type === "polyline" && g.latlngs) {
        layer = L.polyline(g.latlngs, { ...style, dashArray: "5 5" });
      }
      if (!layer) continue;
      layer._overlayShapeId = s.id;
      layer._overlayShapeName = s.name || "";
      layer._overlayShapeDescription = s.description || "";
      if (s.name) {
        layer.bindTooltip(s.name, {
          permanent: true,
          direction: "top",
          className: "overlay-shape-label",
        });
      }
      group.addLayer(layer);
    }
    // Attach geoman if editing
    if (canEdit) {
      group.eachLayer((l) => {
        if (l.pm && !l.pm.enabled()) {
          l.pm.enable({ allowSelfIntersection: false });
          l.pm.disable();
        }
      });
    }
  }, [map, overlay?.id, shapesKey, canEdit]);

  // save handler (debounced)
  const scheduleSave = () => {
    if (!overlayIdRef.current) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(async () => {
      const group = groupRef.current;
      if (!group || !overlayIdRef.current) return;
      const shapes = [];
      group.eachLayer((l) => {
        const s = serialiseLayer(l);
        if (s) shapes.push(s);
      });
      pendingSaveRef.current = true;
      try {
        await replaceOverlayShapes(overlayIdRef.current, shapes);
      } catch (e) {
        pendingSaveRef.current = false;
        toast.error("Failed to save overlay");
      }
    }, 400);
  };

  useEffect(() => {
    if (!map || !canEdit) return;
    const group = groupRef.current;
    const onCreate = (e) => {
      const layer = e.layer;
      if (!layer) return;
      // move new drawings into our tracked group
      map.removeLayer(layer);
      layer._overlayShapeId = crypto.randomUUID();
      const label = window.prompt("Label for this shape (optional):", "");
      if (label) {
        layer._overlayShapeName = label;
        layer.bindTooltip(label, {
          permanent: true,
          direction: "top",
          className: "overlay-shape-label",
        });
      }
      group.addLayer(layer);
      scheduleSave();
    };
    const onEdit = () => scheduleSave();
    const onRemove = (e) => {
      const layer = e.layer;
      if (layer) groupRef.current?.removeLayer(layer);
      scheduleSave();
    };
    map.on("pm:create", onCreate);
    map.on("pm:edit", onEdit);
    map.on("pm:dragend", onEdit);
    map.on("pm:remove", onRemove);
    return () => {
      map.off("pm:create", onCreate);
      map.off("pm:edit", onEdit);
      map.off("pm:dragend", onEdit);
      map.off("pm:remove", onRemove);
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, canEdit]);

  return null;
}
