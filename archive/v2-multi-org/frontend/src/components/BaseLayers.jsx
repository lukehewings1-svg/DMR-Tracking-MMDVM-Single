import { LayersControl, TileLayer } from "react-leaflet";

/**
 * Shared basemap layer picker. Renders a Leaflet LayersControl in the top-right
 * of the map with 4 base layers (exclusive) and a Street-Labels overlay
 * (toggleable, useful over Satellite for a hybrid view).
 *
 *   Base layers (all free, NO API KEY required):
 *     - Dark      : Esri Dark Grey Canvas (tactical look)
 *     - Streets   : OpenStreetMap
 *     - Satellite : Esri World Imagery (high-res photography)
 *     - Terrain   : OpenTopoMap (contours + shaded relief)
 *
 *   Overlays:
 *     - Street labels : Esri Reference labels. Turn on when Satellite or Dark
 *       is selected for a "hybrid" road-name overlay.
 */
export function BaseLayers({ defaultLayer = "Dark" }) {
  return (
    <LayersControl position="topright" collapsed>
      <LayersControl.BaseLayer name="Dark" checked={defaultLayer === "Dark"}>
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
          attribution='Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ'
          maxZoom={16}
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
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
          attribution='Labels &copy; Esri'
          maxZoom={16}
        />
      </LayersControl.Overlay>
    </LayersControl>
  );
}
