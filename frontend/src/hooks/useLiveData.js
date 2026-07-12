import { useEffect, useRef, useState, useCallback } from "react";
import {
  fetchRadios,
  fetchStatus,
  fetchPackets,
  listGeofences,
  listAlerts,
  clearAlerts as clearAlertsApi,
  listGroups,
  listMessages,
  listRepeaters,
  listEmergencies,
  wsUrl,
  TOKEN_KEY,
} from "@/lib/api";
import { toast } from "sonner";

export function useLiveData() {
  const [radios, setRadios] = useState([]);
  const [packets, setPackets] = useState([]);
  const [status, setStatus] = useState(null);
  const [geofences, setGeofences] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [groups, setGroups] = useState([]);
  const [messages, setMessages] = useState([]);
  const [repeaters, setRepeaters] = useState([]);
  const [emergencies, setEmergencies] = useState([]);
  const [voiceActivity, setVoiceActivity] = useState([]);
  const [connected, setConnected] = useState(false);
  const [lastEventAt, setLastEventAt] = useState(null);
  const flashedRef = useRef(new Set());
  const wsRef = useRef(null);

  const refreshAll = useCallback(async () => {
    try {
      const [r, p, s, g, a, gs, ms, rp, em] = await Promise.all([
        fetchRadios(),
        fetchPackets(200),
        fetchStatus(),
        listGeofences(),
        listAlerts(100),
        listGroups(),
        listMessages(200),
        listRepeaters(),
        listEmergencies("active"),
      ]);
      setRadios(r);
      setPackets(p);
      setStatus(s);
      setGeofences(g);
      setAlerts(a);
      setGroups(gs);
      setMessages(ms);
      setRepeaters(rp);
      setEmergencies(em);
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
        group_id: packet.group_id ?? prev[idx]?.group_id ?? null,
        last_lat: packet.lat,
        last_lon: packet.lon,
        last_seen: packet.timestamp,
        last_format: packet.format,
        last_speed: packet.speed ?? null,
        last_heading: packet.heading ?? null,
        last_rssi: packet.rssi ?? null,
        last_source: packet.source,
        last_talkgroup: packet.talkgroup_id ?? prev[idx]?.last_talkgroup ?? null,
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

  const applyEmergency = useCallback((emg) => {
    setEmergencies((prev) => [emg, ...prev.filter((e) => e.id !== emg.id)]);
    setRadios((prev) =>
      prev.map((r) =>
        r.dmr_id === emg.dmr_id
          ? { ...r, in_emergency: true, emergency_id: emg.id, emergency_at: emg.timestamp }
          : r
      )
    );
    toast.error(`EMERGENCY: ${emg.callsign || `ID ${emg.dmr_id}`}`, {
      description: "Radio panic button pressed",
      duration: 15000,
    });
    // Trigger siren
    playSiren();
  }, []);

  const applyEmergencyCleared = useCallback((emergency_id, dmr_id) => {
    setEmergencies((prev) => prev.filter((e) => e.id !== emergency_id));
    setRadios((prev) =>
      prev.map((r) => (r.dmr_id === dmr_id ? { ...r, in_emergency: false } : r))
    );
  }, []);

  const applyMessage = useCallback((msg) => {
    setMessages((prev) => [msg, ...prev].slice(0, 200));
    if (msg.direction === "in") {
      toast(msg.callsign || `ID ${msg.from_dmr_id}`, {
        description: `${msg.text.substring(0, 80)}`,
        duration: 4000,
      });
    }
  }, []);

  useEffect(() => {
    refreshAll();
    const poll = setInterval(refreshAll, 20000);
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
              setEmergencies([]);
            } else if (msg.type === "radio_update") applyRadioUpdate(msg.dmr_id, msg.updates);
            else if (msg.type === "alert") applyAlert(msg.alert);
            else if (msg.type === "emergency") applyEmergency(msg.emergency);
            else if (msg.type === "emergency_cleared")
              applyEmergencyCleared(msg.emergency_id, msg.dmr_id);
            else if (msg.type === "message") applyMessage(msg.message);
            else if (msg.type === "voice_activity") setVoiceActivity(msg.activity || []);
            else if (msg.type === "groups_changed") listGroups().then(setGroups);
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
  }, [applyPacket, applyRadioUpdate, applyAlert, applyEmergency, applyEmergencyCleared, applyMessage]);

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
    groups,
    messages,
    repeaters,
    emergencies,
    voiceActivity,
    connected,
    lastEventAt,
    refreshAll,
    clearAllAlerts,
    consumeFlash,
    setGroups,
    setMessages,
  };
}

// ------------ Siren (Web Audio API) ------------
let sirenTimer = null;
function playSiren() {
  try {
    // eslint-disable-next-line no-undef
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + 0.05);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();

    // whoop-whoop siren over 3 seconds
    let t = ctx.currentTime;
    for (let i = 0; i < 6; i++) {
      osc.frequency.setValueAtTime(880, t);
      osc.frequency.exponentialRampToValueAtTime(440, t + 0.25);
      osc.frequency.exponentialRampToValueAtTime(880, t + 0.5);
      t += 0.5;
    }
    gain.gain.setValueAtTime(0.25, ctx.currentTime + 2.9);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 3.0);
    osc.stop(ctx.currentTime + 3.05);
    clearTimeout(sirenTimer);
    sirenTimer = setTimeout(() => ctx.close(), 3500);
  } catch {
    /* audio blocked - ignore */
  }
}
