import { useEffect, useRef, useState, useCallback } from "react";
import {
  fetchRadios,
  fetchStatus,
  fetchPackets,
  listGeofences,
  listAlerts,
  clearAlerts as clearAlertsApi,
  wsUrl,
  TOKEN_KEY,
} from "@/lib/api";
import { toast } from "sonner";

/**
 * Central state hook: initial REST loads + websocket for live updates + REST
 * polling fallback so the dashboard still updates if the websocket drops.
 */
export function useLiveData() {
  const [radios, setRadios] = useState([]);
  const [packets, setPackets] = useState([]);
  const [status, setStatus] = useState(null);
  const [geofences, setGeofences] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [connected, setConnected] = useState(false);
  const [lastEventAt, setLastEventAt] = useState(null);
  const flashedRef = useRef(new Set());
  const wsRef = useRef(null);

  const refreshAll = useCallback(async () => {
    try {
      const [r, p, s, g, a] = await Promise.all([
        fetchRadios(),
        fetchPackets(200),
        fetchStatus(),
        listGeofences(),
        listAlerts(100),
      ]);
      setRadios(r);
      setPackets(p);
      setStatus(s);
      setGeofences(g);
      setAlerts(a);
    } catch {
      /* noop */
    }
  }, []);

  const clearAllAlerts = useCallback(async () => {
    await clearAlertsApi();
    setAlerts([]);
  }, []);

  const applyPacket = useCallback((packet) => {
    setLastEventAt(Date.now());
    flashedRef.current.add(packet.dmr_id);
    setPackets((prev) => [packet, ...prev].slice(0, 200));
    setRadios((prev) => {
      const idx = prev.findIndex((r) => r.dmr_id === packet.dmr_id);
      const merged = {
        ...(idx >= 0 ? prev[idx] : {}),
        dmr_id: packet.dmr_id,
        callsign: packet.callsign ?? prev[idx]?.callsign ?? null,
        icon: prev[idx]?.icon || "Radio",
        color: prev[idx]?.color || "#39ff14",
        last_lat: packet.lat,
        last_lon: packet.lon,
        last_seen: packet.timestamp,
        last_format: packet.format,
        last_speed: packet.speed ?? null,
        last_heading: packet.heading ?? null,
        last_rssi: packet.rssi ?? null,
        last_source: packet.source,
        position_count: (prev[idx]?.position_count || 0) + 1,
        first_seen: prev[idx]?.first_seen || packet.timestamp,
      };
      const next = idx >= 0 ? [...prev] : [merged, ...prev];
      if (idx >= 0) next[idx] = merged;
      next.sort((a, b) => (a.last_seen < b.last_seen ? 1 : -1));
      return next;
    });
  }, []);

  const applyRadioUpdate = useCallback((dmrId, updates) => {
    setRadios((prev) =>
      prev.map((r) => (r.dmr_id === dmrId ? { ...r, ...updates } : r))
    );
  }, []);

  const applyAlert = useCallback((alert) => {
    setAlerts((prev) => [alert, ...prev].slice(0, 100));
    toast(
      `${alert.callsign || `ID ${alert.dmr_id}`} ${alert.event}ed ${alert.fence_name}`,
      { description: "Geofence alert", duration: 5000 }
    );
  }, []);

  useEffect(() => {
    refreshAll();
    const poll = setInterval(refreshAll, 15000);
    return () => clearInterval(poll);
  }, [refreshAll]);

  useEffect(() => {
    let cancelled = false;
    const connect = () => {
      if (cancelled) return;
      if (!localStorage.getItem(TOKEN_KEY)) return;
      try {
        const ws = new WebSocket(wsUrl());
        wsRef.current = ws;
        ws.onopen = () => setConnected(true);
        ws.onclose = () => {
          setConnected(false);
          if (!cancelled) setTimeout(connect, 3000);
        };
        ws.onerror = () => {
          try {
            ws.close();
          } catch {
            /* noop */
          }
        };
        ws.onmessage = (evt) => {
          try {
            const msg = JSON.parse(evt.data);
            if (msg.type === "packet") applyPacket(msg.packet);
            else if (msg.type === "clear") {
              setRadios([]);
              setPackets([]);
            } else if (msg.type === "radio_update") {
              applyRadioUpdate(msg.dmr_id, msg.updates);
            } else if (msg.type === "alert") {
              applyAlert(msg.alert);
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
  }, [applyPacket, applyRadioUpdate, applyAlert]);

  const consumeFlash = useCallback((dmrId) => {
    if (flashedRef.current.has(dmrId)) {
      flashedRef.current.delete(dmrId);
      return true;
    }
    return false;
  }, []);

  return {
    radios,
    packets,
    status,
    geofences,
    alerts,
    connected,
    lastEventAt,
    refreshAll,
    clearAllAlerts,
    consumeFlash,
  };
}
