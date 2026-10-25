import { useEffect, useMemo, useRef } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import { updateOverlayImage } from "@/lib/api";

/**
 * When the admin is editing a specific overlay set, we drop two draggable
 * "corner" markers on every image in that set. Dragging them updates the
 * imageOverlay bounds live and PATCHes the backend on drag-end.
 */
export function OverlayImageCorners({ overlay }) {
  const map = useMap();
  const groupRef = useRef(null);
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;

  const key = useMemo(
    () =>
      JSON.stringify(
        (overlay?.images || []).map((i) => [i.id, i.bounds, i.opacity])
      ),
    [overlay]
  );

  useEffect(() => {
    if (!map) return;
    if (!groupRef.current) {
      groupRef.current = L.layerGroup().addTo(map);
    }
    const group = groupRef.current;
    group.clearLayers();

    if (!overlay || !(overlay.images || []).length) return;

    // Also grab any leaflet imageOverlays we can find so we can move them
    // as the corners drag (they're managed by React, so we re-find them
    // each drag by iterating map layers).
    const findImageOverlayByUrl = (url) => {
      let found = null;
      map.eachLayer((l) => {
        if (l instanceof L.ImageOverlay && !found) {
          try {
            if (l._url && (l._url === url || l._url.endsWith(url))) {
              found = l;
            }
          } catch {
            /* noop */
          }
        }
      });
      return found;
    };

    overlay.images.forEach((img) => {
      const [sw, ne] = img.bounds || [];
      if (!sw || !ne) return;

      const makeHandle = (latLng, role, other) => {
        const marker = L.marker(latLng, {
          draggable: true,
          icon: L.divIcon({
            className: "",
            iconSize: [16, 16],
            iconAnchor: [8, 8],
            html: `<div style="width:14px;height:14px;background:#00f0ff;
                              border:2px solid #050505;
                              box-shadow:0 0 0 1px #00f0ff,0 0 6px #00f0ff;
                              transform:rotate(45deg);"></div>`,
          }),
        });
        marker.on("drag", () => {
          const p = marker.getLatLng();
          const bounds =
            role === "sw"
              ? L.latLngBounds([p, other])
              : L.latLngBounds([other, p]);
          const io = findImageOverlayByUrl(img.url);
          if (io) io.setBounds(bounds);
        });
        marker.on("dragend", async () => {
          const p = marker.getLatLng();
          const bounds =
            role === "sw"
              ? [
                  [p.lat, p.lng],
                  [other.lat, other.lng],
                ]
              : [
                  [other.lat, other.lng],
                  [p.lat, p.lng],
                ];
          try {
            await updateOverlayImage(overlayRef.current.id, img.id, { bounds });
          } catch {
            /* noop */
          }
        });
        return marker;
      };

      const swLL = L.latLng(sw[0], sw[1]);
      const neLL = L.latLng(ne[0], ne[1]);
      group.addLayer(makeHandle(swLL, "sw", neLL));
      group.addLayer(makeHandle(neLL, "ne", swLL));
    });

    return () => {
      group.clearLayers();
    };
  }, [map, key, overlay]);

  useEffect(() => () => {
    if (groupRef.current) {
      groupRef.current.clearLayers();
      groupRef.current.remove();
      groupRef.current = null;
    }
  }, []);

  return null;
}
