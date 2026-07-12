import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { fetchPositions, updateRadio, deleteRadio, clearEmergency } from "@/lib/api";
import { ICON_SET, COLOR_SET, iconFor } from "@/lib/icons";
import { formatDistanceToNowStrict, format } from "date-fns";
import { Save, Trash2, AlertOctagon } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { PTTButton } from "@/components/PTTButton";

export function RadioDetailModal({ dmrId, radio, groups, onClose, onSaved, onDeleted }) {
  const { user } = useAuth();
  const [positions, setPositions] = useState([]);
  const [callsign, setCallsign] = useState("");
  const [icon, setIcon] = useState("Radio");
  const [color, setColor] = useState("#39ff14");
  const [notes, setNotes] = useState("");
  const [groupId, setGroupId] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!dmrId) return;
    setCallsign(radio?.callsign || "");
    setIcon(radio?.icon || "Radio");
    setColor(radio?.color || "#39ff14");
    setNotes(radio?.notes || "");
    setGroupId(radio?.group_id || "");
    setLoading(true);
    fetchPositions(dmrId)
      .then(setPositions)
      .finally(() => setLoading(false));
  }, [dmrId, radio]);

  const stats = useMemo(() => {
    if (!positions.length) return null;
    let dist = 0;
    for (let i = 1; i < positions.length; i++) {
      dist += haversineKm(
        positions[i - 1].lat, positions[i - 1].lon,
        positions[i].lat, positions[i].lon
      );
    }
    const speeds = positions.map((p) => p.speed).filter((v) => v != null);
    const maxSpeed = speeds.length ? Math.max(...speeds) : null;
    return { dist, maxSpeed };
  }, [positions]);

  const selectedGroup = groups?.find((g) => g.id === groupId);

  const save = async () => {
    await updateRadio(dmrId, {
      callsign: callsign || null,
      icon,
      color,
      notes: notes || null,
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

  const SelectedIcon = iconFor(icon);
  const canDelete = user?.role === "admin";
  const canClearEmg = user?.role === "admin" && radio?.in_emergency;

  return (
    <Dialog open={!!dmrId} onOpenChange={(v) => !v && onClose?.()}>
      <DialogContent
        data-testid="radio-detail"
        className="max-w-5xl bg-[#0a0a0a] border-[#2a2a2a] text-neutral-100 rounded-none p-0"
      >
        <DialogHeader className="border-b border-[#2a2a2a] p-4 space-y-1">
          <DialogTitle className="flex items-center gap-3 text-lg">
            <div
              className="flex h-9 w-9 items-center justify-center border"
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
              <div className="mono text-base text-neutral-100">
                {radio?.callsign || "— unassigned —"}
              </div>
            </div>
          </DialogTitle>
          <DialogDescription className="mono text-[10px] text-neutral-500">
            Live status, position history, PTT and DMR messaging for this radio.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 p-4 md:grid-cols-2">
          {/* Left: metadata form + PTT */}
          <div className="space-y-4">
            {canClearEmg && (
              <button
                data-testid="detail-clear-emergency"
                onClick={clearDistress}
                className="flex w-full items-center justify-center gap-2 border-2 border-[#ff3b30] bg-[#ff3b30] px-3 py-2 mono text-[11px] uppercase tracking-widest text-black hover:bg-black hover:text-[#ff3b30]"
              >
                <AlertOctagon className="h-4 w-4" /> Acknowledge / Clear Emergency
              </button>
            )}

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
                    {g.name} · TG {g.talkgroup_id}
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

            <div className="border-t border-[#2a2a2a] pt-3">
              <div className="mono mb-1 text-[10px] uppercase tracking-widest text-neutral-500">
                Voice Contact
              </div>
              <PTTButton
                targetDmrId={dmrId}
                callerCallsign={user?.callsign || "control"}
              />
              {selectedGroup && (
                <div className="mt-2">
                  <PTTButton
                    groupId={selectedGroup.id}
                    groupName={selectedGroup.name}
                    callerCallsign={user?.callsign || "control"}
                  />
                </div>
              )}
            </div>
          </div>

          {/* Right: metrics + history */}
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-2 mono text-[11px]">
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

            <div className="border border-[#2a2a2a]">
              <div className="flex items-center justify-between border-b border-[#2a2a2a] px-2 py-1 mono text-[10px] uppercase tracking-widest text-neutral-500">
                <span>Position History</span>
                <span>{positions.length} pts</span>
              </div>
              <div data-testid="position-history" className="max-h-72 overflow-y-auto mono text-[11px]">
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
