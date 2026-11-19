import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  fetchPositions,
  updateRadio,
  deleteRadio,
  clearEmergency,
  listShiftLog,
  sendMessage,
} from "@/lib/api";
import { ICON_SET, COLOR_SET, iconFor } from "@/lib/icons";
import { formatDistanceToNowStrict, format } from "date-fns";
import {
  Save,
  Trash2,
  AlertOctagon,
  Radio as RadioIcon,
  MessageSquare,
  MapPin,
  Send,
  User,
  Users as UsersIcon,
  Info,
  Mic,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { PTTButton } from "@/components/PTTButton";

const TAB_LIST = [
  { id: "info", label: "Info", icon: Info },
  { id: "voice", label: "Radio", icon: Mic },
  { id: "msg", label: "Message", icon: MessageSquare },
  { id: "positions", label: "Track", icon: MapPin },
  { id: "history", label: "TX History", icon: RadioIcon },
];

export function RadioDetailModal({
  dmrId,
  radio,
  groups,
  messages,
  onClose,
  onSaved,
  onDeleted,
}) {
  const { user } = useAuth();
  const [tab, setTab] = useState("info");
  const [positions, setPositions] = useState([]);
  const [voiceLog, setVoiceLog] = useState([]);
  const [callsign, setCallsign] = useState("");
  const [icon, setIcon] = useState("Radio");
  const [color, setColor] = useState("#39ff14");
  const [notes, setNotes] = useState("");
  const [crew, setCrew] = useState("");
  const [groupId, setGroupId] = useState("");
  const [loading, setLoading] = useState(true);
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    if (!dmrId) return;
    setCallsign(radio?.callsign || "");
    setIcon(radio?.icon || "Radio");
    setColor(radio?.color || "#39ff14");
    setNotes(radio?.notes || "");
    setCrew(radio?.crew || "");
    setGroupId(radio?.group_id || "");
    setTab("info");
    setLoading(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dmrId]);

  const lastSeen = radio?.last_seen;
  useEffect(() => {
    if (!dmrId) return;
    fetchPositions(dmrId)
      .then(setPositions)
      .finally(() => setLoading(false));
  }, [dmrId, lastSeen]);

  useEffect(() => {
    if (!dmrId || tab !== "history") return;
    setVoiceLoading(true);
    listShiftLog({ dmr_id: dmrId, event_type: "voice", limit: 200 })
      .then(setVoiceLog)
      .catch(() => setVoiceLog([]))
      .finally(() => setVoiceLoading(false));
  }, [dmrId, tab]);

  const stats = useMemo(() => {
    if (!positions.length) return null;
    let dist = 0;
    for (let i = 1; i < positions.length; i++) {
      dist += haversineKm(
        positions[i - 1].lat, positions[i - 1].lon,
        positions[i].lat, positions[i].lon,
      );
    }
    const speeds = positions.map((p) => p.speed).filter((v) => v != null);
    const maxSpeed = speeds.length ? Math.max(...speeds) : null;
    return { dist, maxSpeed };
  }, [positions]);

  const selectedGroup = groups?.find((g) => g.id === groupId);

  const radioMessages = useMemo(() => {
    if (!messages || !dmrId) return [];
    return messages
      .filter(
        (m) =>
          m.from_dmr_id === dmrId ||
          m.to_dmr_id === dmrId ||
          (m.is_private && (m.from_dmr_id === dmrId || m.to_dmr_id === dmrId)),
      )
      .sort((a, b) => (a.timestamp > b.timestamp ? 1 : -1));
  }, [messages, dmrId]);

  const save = async () => {
    await updateRadio(dmrId, {
      callsign: callsign || null,
      icon,
      color,
      notes: notes || null,
      crew: crew || null,
      group_id: groupId || null,
    });
    toast.success("Radio updated");
    onSaved?.();
  };

  const remove = async () => {
    if (!window.confirm(`Delete radio ${dmrId} and its history?`)) return;
    await deleteRadio(dmrId);
    toast.success("Radio deleted");
    onDeleted?.();
  };

  const clearDistress = async () => {
    if (!radio?.emergency_id) return;
    try {
      await clearEmergency(radio.emergency_id);
      toast.success("Emergency cleared");
      onSaved?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const sendDirectMessage = async () => {
    if (!draft.trim()) return;
    try {
      await sendMessage({ text: draft, target_dmr_id: dmrId });
      toast.success("Message queued");
      setDraft("");
      // NB: don't call onSaved() here — it triggers a parent-level refresh
      // that unmounts and remounts the modal, closing it before the operator
      // sees the sent message land in history via the live WebSocket push.
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    }
  };

  const SelectedIcon = iconFor(icon);
  const canDelete = user?.role === "admin";
  const canClearEmg = user?.role === "admin" && radio?.in_emergency;

  return (
    <Dialog open={!!dmrId} onOpenChange={(v) => !v && onClose?.()}>
      <DialogContent
        data-testid="radio-detail"
        className="max-w-5xl w-[95vw] max-h-[90vh] overflow-hidden bg-[#0a0a0a] border-[#2a2a2a] text-neutral-100 rounded-none p-0 flex flex-col"
      >
        <DialogHeader className="border-b border-[#2a2a2a] p-4 space-y-1 shrink-0">
          <DialogTitle className="flex items-center gap-3 text-lg">
            <div
              className="flex h-9 w-9 items-center justify-center border shrink-0"
              style={{ color, borderColor: color + "60" }}
            >
              <SelectedIcon className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                DMR ID {dmrId}
                {radio?.in_emergency && (
                  <span className="ml-2 text-[#ff3b30]">· IN DISTRESS</span>
                )}
              </div>
              <div className="mono text-base text-neutral-100 truncate">
                {radio?.callsign || "— unassigned —"}
              </div>
            </div>
          </DialogTitle>
          <DialogDescription className="mono text-[10px] text-neutral-500">
            Voice contact, direct messaging, tracking history and transmission log.
          </DialogDescription>
        </DialogHeader>

        {canClearEmg && (
          <div className="border-b border-[#2a2a2a] px-4 py-2 shrink-0">
            <button
              data-testid="detail-clear-emergency"
              onClick={clearDistress}
              className="flex w-full items-center justify-center gap-2 border-2 border-[#ff3b30] bg-[#ff3b30] px-3 py-2 mono text-[11px] uppercase tracking-widest text-black hover:bg-black hover:text-[#ff3b30]"
            >
              <AlertOctagon className="h-4 w-4" /> Acknowledge / Clear Emergency
            </button>
          </div>
        )}

        {/* Tabs */}
        <div className="flex shrink-0 overflow-x-auto border-b border-[#2a2a2a]">
          {TAB_LIST.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                data-testid={`detail-tab-${t.id}`}
                onClick={() => setTab(t.id)}
                className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap border-r border-[#2a2a2a] px-3 py-2 mono text-[11px] uppercase tracking-widest transition-colors ${
                  active
                    ? "bg-[#001a1f] text-[#00f0ff]"
                    : "text-neutral-400 hover:bg-[#111] hover:text-neutral-100"
                }`}
              >
                <Icon className="h-3.5 w-3.5" /> {t.label}
              </button>
            );
          })}
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto">
          {tab === "info" && (
            <div className="grid gap-4 p-4 md:grid-cols-2">
              {/* Left: metadata form */}
              <div className="space-y-4">
                <Field label="Callsign">
                  <input
                    data-testid="detail-callsign"
                    value={callsign}
                    onChange={(e) => setCallsign(e.target.value.toUpperCase())}
                    maxLength={16}
                    className="w-full border border-[#2a2a2a] bg-black px-3 py-2 mono text-sm uppercase tracking-wider text-neutral-100 outline-none focus:border-[#00f0ff]"
                  />
                </Field>
                <Field label="Group">
                  <select
                    data-testid="detail-group"
                    value={groupId}
                    onChange={(e) => setGroupId(e.target.value)}
                    className="w-full border border-[#2a2a2a] bg-black px-3 py-2 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
                  >
                    <option value="">— none —</option>
                    {(groups || []).map((g) => (
                      <option key={g.id} value={g.id}>
                        {`${g.name} · TG ${g.talkgroup_id}`}
                      </option>
                    ))}
                  </select>
                </Field>
                <div>
                  <div className="mono mb-1 text-[10px] uppercase tracking-widest text-neutral-500">
                    Map Icon
                  </div>
                  <div className="grid grid-cols-9 gap-1" data-testid="icon-picker">
                    {ICON_SET.map(({ key, Icon }) => (
                      <button
                        key={key}
                        data-testid={`icon-${key}`}
                        type="button"
                        onClick={() => setIcon(key)}
                        title={key}
                        className={`flex aspect-square items-center justify-center border transition-colors ${
                          icon === key
                            ? "border-[#00f0ff] bg-[#001a1f] text-[#00f0ff]"
                            : "border-[#2a2a2a] text-neutral-400 hover:border-neutral-500 hover:text-neutral-100"
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="mono mb-1 text-[10px] uppercase tracking-widest text-neutral-500">
                    Color
                  </div>
                  <div className="flex gap-1.5" data-testid="color-picker">
                    {COLOR_SET.map(({ key, label }) => (
                      <button
                        key={key}
                        data-testid={`color-${label.toLowerCase()}`}
                        type="button"
                        onClick={() => setColor(key)}
                        className={`h-6 w-6 border transition-transform ${
                          color === key ? "scale-110 border-white" : "border-[#2a2a2a] hover:scale-105"
                        }`}
                        style={{ background: key }}
                      />
                    ))}
                  </div>
                </div>
                <Field label="Crew / unit details">
                  <textarea
                    data-testid="detail-crew"
                    value={crew}
                    onChange={(e) => setCrew(e.target.value)}
                    rows={2}
                    placeholder="e.g. Unit 3 · J. Smith (lead), A. Patel · Medic"
                    className="w-full border border-[#2a2a2a] bg-black px-3 py-2 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
                  />
                </Field>
                <Field label="Notes">
                  <textarea
                    data-testid="detail-notes"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    rows={2}
                    className="w-full border border-[#2a2a2a] bg-black px-3 py-2 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
                  />
                </Field>
                <div className="flex gap-2">
                  <button
                    data-testid="detail-save"
                    onClick={save}
                    className="flex items-center gap-1.5 border border-[#39ff14] bg-[#0a1a0a] px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14] hover:text-black"
                  >
                    <Save className="h-3 w-3" /> Save
                  </button>
                  {canDelete && (
                    <button
                      data-testid="detail-delete"
                      onClick={remove}
                      className="flex items-center gap-1.5 border border-[#ff3b30]/60 bg-[#1a0505] px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#ff3b30] hover:bg-[#ff3b30] hover:text-black"
                    >
                      <Trash2 className="h-3 w-3" /> Delete
                    </button>
                  )}
                </div>
              </div>
              {/* Right: stats */}
              <div className="grid h-fit grid-cols-2 gap-2 mono text-[11px]">
                <StatBox label="Positions" value={positions.length} />
                <StatBox
                  label="Last Heard"
                  value={radio?.last_seen ? formatDistanceToNowStrict(new Date(radio.last_seen)) + " ago" : "—"}
                />
                <StatBox label="Trail Length" value={stats ? `${stats.dist.toFixed(2)} km` : "—"} />
                <StatBox label="Max Speed" value={stats?.maxSpeed != null ? `${stats.maxSpeed} kph` : "—"} />
                <StatBox label="Format" value={radio?.last_format || "—"} />
                <StatBox label="Last RSSI" value={radio?.last_rssi != null ? radio.last_rssi + " dBm" : "—"} />
                <StatBox label="Talkgroup" value={radio?.last_talkgroup ?? "—"} />
                <StatBox label="Repeater" value={radio?.last_repeater_id ?? "—"} />
              </div>
            </div>
          )}

          {tab === "voice" && (
            <div className="space-y-4 p-4" data-testid="detail-voice-panel">
              <div className="border border-[#2a2a2a] bg-[#0a0a0a] p-4">
                <div className="mono mb-2 flex items-center gap-2 text-[10px] uppercase tracking-widest text-[#00f0ff]">
                  <User className="h-3 w-3" /> Private call to {radio?.callsign || `ID ${dmrId}`}
                </div>
                <PTTButton
                  callType="private"
                  targetId={dmrId}
                  label={radio?.callsign || `ID ${dmrId}`}
                  callerCallsign={user?.callsign || "control"}
                  testid="detail-ptt-private"
                />
                <p className="mt-2 mono text-[10px] text-neutral-500">
                  Live voice goes out through the AMBE dongle (server) or a DMR818
                  gateway. With neither connected it sends a DMR text asking the
                  operator to call in.
                </p>
              </div>
              {selectedGroup && (
                <div className="border border-[#2a2a2a] bg-[#0a0a0a] p-4">
                  <div className="mono mb-2 flex items-center gap-2 text-[10px] uppercase tracking-widest text-[#39ff14]">
                    <UsersIcon className="h-3 w-3" /> Group call · {selectedGroup.name} (TG {selectedGroup.talkgroup_id})
                  </div>
                  <PTTButton
                    callType="group"
                    targetId={selectedGroup.talkgroup_id}
                    groupId={selectedGroup.id}
                    label={selectedGroup.name}
                    callerCallsign={user?.callsign || "control"}
                    testid="detail-ptt-group"
                  />
                  <p className="mt-2 mono text-[10px] text-neutral-500">
                    Broadcasts to every radio on TG {selectedGroup.talkgroup_id} across all connected MMDVMs.
                  </p>
                </div>
              )}
            </div>
          )}

          {tab === "msg" && (
            <div className="flex h-[60vh] flex-col p-4" data-testid="detail-msg-panel">
              <div className="mono mb-2 flex items-center justify-between text-[10px] uppercase tracking-widest text-neutral-500">
                <span>Direct messages with {radio?.callsign || `ID ${dmrId}`}</span>
                <span>{radioMessages.length} msg</span>
              </div>
              <div
                className="flex-1 overflow-y-auto border border-[#2a2a2a] bg-black p-2 mono text-[11px]"
                data-testid="detail-msg-history"
              >
                {radioMessages.length === 0 && (
                  <div className="text-neutral-600">// no messages yet</div>
                )}
                {radioMessages.map((m) => {
                  const outbound = m.direction === "out";
                  const t = m.timestamp ? format(new Date(m.timestamp), "HH:mm:ss") : "";
                  return (
                    <div
                      key={m.id}
                      className={`mb-2 flex ${outbound ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[85%] border px-2 py-1 ${
                          outbound
                            ? "border-[#39ff14]/40 bg-[#0a1a0a] text-neutral-100"
                            : "border-[#00f0ff]/40 bg-[#001a1f] text-neutral-100"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 text-[9px] text-neutral-500">
                          <span>
                            {outbound
                              ? `→ ${m.is_private ? `ID ${m.to_dmr_id}` : `TG ${m.talkgroup_id}`}`
                              : `← ${m.callsign || `ID ${m.from_dmr_id}`}`}
                          </span>
                          <span>{t}</span>
                        </div>
                        <div className="whitespace-pre-wrap">{m.text}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-2 flex items-end gap-1">
                <textarea
                  data-testid="detail-msg-input"
                  rows={2}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) sendDirectMessage();
                  }}
                  placeholder={`Message ${radio?.callsign || `ID ${dmrId}`} directly (Ctrl+Enter to send)`}
                  className="flex-1 border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] text-neutral-100 outline-none focus:border-[#00f0ff]"
                />
                <button
                  data-testid="detail-msg-send"
                  onClick={sendDirectMessage}
                  disabled={!draft.trim()}
                  className="flex h-full min-h-[46px] items-center gap-1 border border-[#39ff14] bg-[#0a1a0a] px-3 mono text-[10px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14] hover:text-black disabled:opacity-40"
                >
                  <Send className="h-3 w-3" /> Send
                </button>
              </div>
            </div>
          )}

          {tab === "positions" && (
            <div className="p-4" data-testid="detail-positions-panel">
              <div className="border border-[#2a2a2a]">
                <div className="flex items-center justify-between border-b border-[#2a2a2a] px-2 py-1 mono text-[10px] uppercase tracking-widest text-neutral-500">
                  <span>Position History</span>
                  <span>{positions.length} pts</span>
                </div>
                <div data-testid="position-history" className="max-h-[60vh] overflow-y-auto mono text-[11px]">
                  {loading && <div className="p-3 text-neutral-600">loading…</div>}
                  {!loading && positions.length === 0 && (
                    <div className="p-3 text-neutral-600">no positions</div>
                  )}
                  {[...positions].reverse().map((p) => (
                    <div
                      key={p.id}
                      className="grid grid-cols-[80px_1fr_60px] border-b border-[#1a1a1a] px-2 py-1 last:border-b-0"
                    >
                      <span className="text-neutral-500">
                        {p.timestamp ? format(new Date(p.timestamp), "HH:mm:ss") : "—"}
                      </span>
                      <span className="text-neutral-200">
                        {p.lat.toFixed(5)}, {p.lon.toFixed(5)}
                      </span>
                      <span className="text-right text-neutral-500">
                        {p.speed != null ? `${p.speed}kph` : "—"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {tab === "history" && (
            <div className="p-4" data-testid="detail-tx-panel">
              <div className="border border-[#2a2a2a]">
                <div className="flex items-center justify-between border-b border-[#2a2a2a] px-2 py-1 mono text-[10px] uppercase tracking-widest text-neutral-500">
                  <span>Voice TX history (last 200)</span>
                  <span>{voiceLog.length}</span>
                </div>
                <div className="max-h-[60vh] overflow-y-auto mono text-[11px]" data-testid="tx-history">
                  {voiceLoading && (
                    <div className="p-3 text-neutral-600">loading…</div>
                  )}
                  {!voiceLoading && voiceLog.length === 0 && (
                    <div className="p-3 text-neutral-600">
                      No voice transmissions recorded for this radio yet.
                    </div>
                  )}
                  {voiceLog.map((e) => (
                    <div
                      key={e.id}
                      className="grid grid-cols-[90px_1fr] gap-2 border-b border-[#1a1a1a] px-2 py-1 last:border-b-0"
                    >
                      <span className="text-neutral-500">
                        {e.ts ? format(new Date(e.ts), "HH:mm:ss") : "—"}
                      </span>
                      <span className="text-neutral-200">
                        {e.description || "voice tx"}
                        {e.metadata?.talkgroup_id != null && (
                          <span className="ml-2 text-neutral-500">
                            TG {e.metadata.talkgroup_id}
                          </span>
                        )}
                        {e.metadata?.repeater_id != null && (
                          <span className="ml-2 text-neutral-500">
                            RPT {e.metadata.repeater_id}
                          </span>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mono mb-1 block text-[10px] uppercase tracking-widest text-neutral-500">
        {label}
      </span>
      {children}
    </label>
  );
}

function StatBox({ label, value }) {
  return (
    <div className="border border-[#2a2a2a] px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-widest text-neutral-500">{label}</div>
      <div className="mono text-sm text-neutral-100 mt-0.5">{value}</div>
    </div>
  );
}

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const toRad = (v) => (v * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
