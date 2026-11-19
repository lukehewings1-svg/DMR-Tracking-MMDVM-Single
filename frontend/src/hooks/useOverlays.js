import { useEffect, useState } from "react";
import { listOverlays } from "@/lib/api";

export function useOverlays(lastOverlayEvent) {
  const [overlays, setOverlays] = useState([]);
  const refresh = () => listOverlays().then(setOverlays).catch(() => {});
  useEffect(() => {
    refresh();
  }, [lastOverlayEvent]);
  return [overlays, setOverlays];
}
