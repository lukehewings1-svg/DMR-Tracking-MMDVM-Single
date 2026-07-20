import { useEffect, useState } from "react";
import { useMap } from "react-leaflet";
import { Compass, RotateCcw, RotateCw } from "lucide-react";

/**
 * Small custom control that lets an operator align the map to any bearing —
 * useful when the event site's "north" doesn't match true north (e.g. a race
 * course laid out along a valley or a stadium oriented at 40°).
 *
 * Powered by the `leaflet-rotate` plugin which was imported once at module
 * scope in the app (see MapView.jsx / SituationalView.jsx). The MapContainer
 * must be created with `rotate={true}` to enable the underlying support.
 *
 * Interactions:
 *   • Buttons: ±15° rotate, 0° reset (points north again).
 *   • Keyboard (when map is focused): Shift + ← / → to nudge, Shift + 0 to reset.
 *   • Touch: two-finger twist gesture (provided by leaflet-rotate).
 */
export function RotateControl() {
  const map = useMap();
  const [bearing, setBearing] = useState(0);

  useEffect(() => {
    if (!map || typeof map.getBearing !== "function") return;
    const onRotate = () => setBearing(Math.round(map.getBearing()));
    map.on("rotate", onRotate);
    setBearing(Math.round(map.getBearing()));
    return () => map.off("rotate", onRotate);
  }, [map]);

  const nudge = (deg) => {
    if (typeof map.setBearing !== "function") return;
    map.setBearing((map.getBearing() + deg + 360) % 360);
  };
  const reset = () => {
    if (typeof map.setBearing === "function") map.setBearing(0);
  };

  return (
    <div
      className="leaflet-top leaflet-left"
      style={{ pointerEvents: "auto", marginTop: 80, marginLeft: 10 }}
    >
      <div
        className="leaflet-control flex flex-col items-center gap-1 border border-[#2a2a2a] bg-black/85 p-1"
        data-testid="rotate-control"
      >
        <button
          type="button"
          data-testid="rotate-ccw"
          onClick={() => nudge(-15)}
          className="flex h-7 w-7 items-center justify-center text-neutral-300 hover:text-[#00f0ff]"
          title="Rotate counter-clockwise 15°"
        >
          <RotateCcw className="h-4 w-4" />
        </button>
        <button
          type="button"
          data-testid="rotate-reset"
          onClick={reset}
          className="flex h-8 w-8 items-center justify-center border border-transparent text-neutral-100 hover:border-[#00f0ff] hover:text-[#00f0ff]"
          title="Reset bearing to north"
          style={{
            transform: `rotate(${-bearing}deg)`,
            transition: "transform 200ms ease",
          }}
        >
          <Compass className="h-5 w-5" />
        </button>
        <button
          type="button"
          data-testid="rotate-cw"
          onClick={() => nudge(15)}
          className="flex h-7 w-7 items-center justify-center text-neutral-300 hover:text-[#00f0ff]"
          title="Rotate clockwise 15°"
        >
          <RotateCw className="h-4 w-4" />
        </button>
        <span
          data-testid="rotate-bearing"
          className="mono text-[9px] uppercase tracking-widest text-neutral-500"
        >
          {bearing}°
        </span>
      </div>
    </div>
  );
}
