import { useState } from "react";
import { Headphones, Radio as RadioIcon, Users, Volume2 } from "lucide-react";
import { PTTButton } from "@/components/PTTButton";
import { voiceClient } from "@/lib/voiceClient";
import { useVoice } from "@/hooks/useVoice";
import { useAuth } from "@/context/AuthContext";

function RouteBadge({ v }) {
  const s = v.status;
  const route = s?.route;
  const text = !v.connected
    ? "voice link offline"
    : route === "dongle"
    ? `AMBE dongle${s.dongle?.product ? ` · ${s.dongle.product}` : ""}`
    : route === "gateway"
    ? `DMR818 gateway · ${s.gateways[0]?.name}`
    : "no voice route";
  const color = !v.connected || !route ? "#ffb800" : "#39ff14";
  return (
    <span data-testid="voice-route" className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest" style={{ color }}>
      <span className="h-1.5 w-1.5" style={{ background: color }} /> {text}
    </span>
  );
}

export function VoicePanel({ groups, radios }) {
  const v = useVoice();
  const { user } = useAuth();
  const [mode, setMode] = useState("group");
  const [tgId, setTgId] = useState("");
  const [radioId, setRadioId] = useState("");
  const g = groups.find((x) => String(x.talkgroup_id) === String(tgId)) || groups[0];
  const r = radios.find((x) => String(x.dmr_id) === String(radioId));
  const targetId = mode === "group" ? g?.talkgroup_id : r?.dmr_id;
  const label = mode === "group" ? g?.name || "talkgroup" : r?.callsign || (r ? `ID ${r.dmr_id}` : "radio");
  const rx = v.rx;

  const seg = (m, icon, text) => (
    <button
      data-testid={`voice-mode-${m}`}
      onClick={() => setMode(m)}
      className={`flex flex-1 items-center justify-center gap-1 border px-2 py-1 uppercase tracking-widest ${
        mode === m ? "border-[#00f0ff] bg-[#001a1f] text-[#00f0ff]" : "border-[#2a2a2a] text-neutral-400 hover:text-neutral-100"
      }`}
    >
      {icon} {text}
    </button>
  );
  const selectCls = "w-full border border-[#2a2a2a] bg-black px-2 py-1.5 text-neutral-100 outline-none focus:border-[#00f0ff]";

  return (
    <div data-testid="voice-panel" className="space-y-2 border-b border-[#2a2a2a] p-3 mono text-[11px]">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">Voice</span>
        <RouteBadge v={v} />
      </div>

      <div className="flex items-center gap-2">
        <button
          data-testid="voice-listen-toggle"
          onClick={() => voiceClient.setListening(!v.listening)}
          className={`flex items-center gap-1.5 border px-2 py-1 uppercase tracking-widest ${
            v.listening ? "border-[#39ff14] text-[#39ff14]" : "border-[#2a2a2a] text-neutral-400 hover:text-neutral-100"
          }`}
        >
          <Headphones className="h-3.5 w-3.5" /> {v.listening ? "Listening" : "Listen"}
        </button>
        <Volume2 className="h-3.5 w-3.5 text-neutral-500" />
        <input
          data-testid="voice-volume"
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={v.volume}
          onChange={(e) => voiceClient.setVolume(Number(e.target.value))}
          className="min-w-0 flex-1 accent-[#00f0ff]"
        />
      </div>

      <div
        data-testid="voice-rx"
        className={`border px-2 py-1.5 ${rx ? "border-[#39ff14] bg-[#0a1a0a] text-[#39ff14]" : "border-[#2a2a2a] text-neutral-600"}`}
      >
        {rx
          ? `RECEIVING · ${rx.callsign || `ID ${rx.src_id}`} · ${rx.private ? "private call" : rx.dst_id ? `TG ${rx.dst_id}` : "group call"}`
          : v.status?.tx
          ? `TRANSMITTING · ${v.status.tx.user} → ${v.status.tx.call_type === "private" ? "ID" : "TG"} ${v.status.tx.target_id}`
          : "// channel quiet"}
      </div>

      <div className="flex gap-1">
        {seg("group", <Users className="h-3 w-3" />, "Talkgroup")}
        {seg("private", <RadioIcon className="h-3 w-3" />, "One radio")}
      </div>
      {mode === "group" ? (
        <select data-testid="voice-target-group" value={g?.talkgroup_id ?? ""} onChange={(e) => setTgId(e.target.value)} className={selectCls}>
          {groups.map((x) => (
            <option key={x.id} value={x.talkgroup_id}>
              {x.name} · TG {x.talkgroup_id}
            </option>
          ))}
        </select>
      ) : (
        <select data-testid="voice-target-radio" value={radioId} onChange={(e) => setRadioId(e.target.value)} className={selectCls}>
          <option value="">Pick a radio…</option>
          {radios.map((x) => (
            <option key={x.dmr_id} value={x.dmr_id}>
              {x.callsign || "—"} · ID {x.dmr_id}
            </option>
          ))}
        </select>
      )}
      <PTTButton callType={mode} targetId={targetId} groupId={g?.id} label={label} callerCallsign={user?.callsign} spaceKey testid="voice-ptt" />
      {v.error && <div data-testid="voice-error" className="text-[#ff3b30]">{v.error}</div>}
      <div className="text-[9px] text-neutral-600">Hold the button or the space bar to talk.</div>
    </div>
  );
}
