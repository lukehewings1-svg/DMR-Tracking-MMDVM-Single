import { LayersControl, TileLayer } from "react-leaflet";

/**
 * Shared basemap layer picker. Renders a Leaflet LayersControl in the top-right
 * of the map with 4 base layers (exclusive) and a Street-Labels overlay
 * (toggleable, useful over Satellite for a hybrid view).
 *
 *   Base layers:
 *     - Dark      : CARTO Dark  (default; tactical look)
 *     - Streets   : OpenStreetMap
 *     - Satellite : Esri World Imagery (high-res photography, no key required)
 *     - Terrain   : OpenTopoMap (contours + shaded relief)
 *
 *   Overlays:
 *     - Street labels : CARTO "labels only" transparent tiles. Turn on when
 *       Satellite is selected for a "hybrid" road-name overlay.
 *
 * All tile providers are free to use with attribution — no API keys.
 */
export function BaseLayers({ defaultLayer = "Dark" }) {
  return (
    <LayersControl position="topright" collapsed>
      <LayersControl.BaseLayer name="Dark" checked={defaultLayer === "Dark"}>
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &middot; &copy; <a href="https://carto.com/attributions">CARTO</a>'
          maxZoom={20}
        />
      </LayersControl.BaseLayer>

      <LayersControl.BaseLayer name="Streets" checked={defaultLayer === "Streets"}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          maxZoom={19}
        />
      </LayersControl.BaseLayer>

      <LayersControl.BaseLayer name="Satellite" checked={defaultLayer === "Satellite"}>
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          attribution='Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
          maxZoom={19}
        />
      </LayersControl.BaseLayer>

      <LayersControl.BaseLayer name="Terrain" checked={defaultLayer === "Terrain"}>
        <TileLayer
          url="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.opentopomap.org">OpenTopoMap</a> (CC-BY-SA)'
          maxZoom={17}
        />
      </LayersControl.BaseLayer>

      <LayersControl.Overlay name="Street labels">
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png"
          attribution='Labels &copy; <a href="https://carto.com/attributions">CARTO</a>'
          maxZoom={20}
        />
      </LayersControl.Overlay>
    </LayersControl>
  );
}
