import { LayerGroup, LayersControl, TileLayer } from "react-leaflet";

const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
const esri = (svc) => `${ESRI}/${svc}/MapServer/tile/{z}/{y}/{x}`;
const IMAGERY_ATTR =
  "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community";

// All layers are Esri public tile services: free, no API key.
// maxNativeZoom lets Leaflet upscale the last real zoom level instead of
// showing "Map data not yet available" tiles when zoomed in close.
export function BaseLayers({ defaultLayer = "Hybrid" }) {
  return (
    <LayersControl position="topright" collapsed>
      <LayersControl.BaseLayer name="Hybrid (satellite + streets)" checked={defaultLayer === "Hybrid"}>
        <LayerGroup>
          <TileLayer url={esri("World_Imagery")} attribution={IMAGERY_ATTR} maxNativeZoom={19} maxZoom={20} />
          <TileLayer url={esri("Reference/World_Transportation")} maxNativeZoom={19} maxZoom={20} />
          <TileLayer url={esri("Reference/World_Boundaries_and_Places")} maxNativeZoom={19} maxZoom={20} />
        </LayerGroup>
      </LayersControl.BaseLayer>

      <LayersControl.BaseLayer name="Streets" checked={defaultLayer === "Streets"}>
        <TileLayer
          url={esri("World_Street_Map")}
          attribution="Tiles &copy; Esri &mdash; Esri, HERE, Garmin, OpenStreetMap contributors"
          maxNativeZoom={19}
          maxZoom={20}
        />
      </LayersControl.BaseLayer>

      <LayersControl.BaseLayer name="Satellite" checked={defaultLayer === "Satellite"}>
        <TileLayer url={esri("World_Imagery")} attribution={IMAGERY_ATTR} maxNativeZoom={19} maxZoom={20} />
      </LayersControl.BaseLayer>

      <LayersControl.BaseLayer name="Terrain" checked={defaultLayer === "Terrain"}>
        <TileLayer
          url={esri("World_Topo_Map")}
          attribution="Tiles &copy; Esri &mdash; Esri, HERE, Garmin, USGS, NGA"
          maxNativeZoom={19}
          maxZoom={20}
        />
      </LayersControl.BaseLayer>

      <LayersControl.BaseLayer name="Dark" checked={defaultLayer === "Dark"}>
        <LayerGroup>
          <TileLayer
            url={esri("Canvas/World_Dark_Gray_Base")}
            attribution="Tiles &copy; Esri &mdash; Esri, HERE, Garmin"
            maxNativeZoom={16}
            maxZoom={20}
          />
          <TileLayer url={esri("Canvas/World_Dark_Gray_Reference")} maxNativeZoom={16} maxZoom={20} />
        </LayerGroup>
      </LayersControl.BaseLayer>
    </LayersControl>
  );
}
