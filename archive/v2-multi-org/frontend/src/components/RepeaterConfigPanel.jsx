import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { listRepeaters, listRepeaterConfigs, upsertRepeaterConfig, deleteRepeaterConfig } from "@/lib/api";
import { toast } from "sonner";
import { Server, Save, Trash2, Cable } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

export function RepeaterConfigPanel({ channels, embedded }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  if (user?.role !== "admin") return null;
  return (
    <div className={embedded ? "px-3 pb-2" : "border-b border-[#2a2a2a] p-3"} data-testid="repeater-config-panel">
      <div className="mb-2 flex items-center justify-between">
        {!embedded && (
          <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">
            MMDVM Channel Bindings
          </div>
        )}
        {embedded && <div />}
        <button
          data-testid="repeater-config-open"
          onClick={() => setOpen(true)}
          className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-0.5 mono text-[10px] uppercase text-neutral-400 hover:border-[#00f0ff] hover:text-[#00f0ff]"
        >
          <Cable className="h-3 w-3" /> Configure
        </button>
      </div>
      <div className="mono text-[10px] text-neutral-500">
        Map each MMDVM&#39;s TS1 and TS2 to any channel (admin only).
      </div>
      <RepeaterConfigModal open={open} onClose={() => setOpen(false)} channels={channels} />
    </div>
  );
}

function RepeaterConfigModal({ open, onClose, channels }) {
  const [rows, setRows] = useState([]);
  const [live, setLive] = useState([]);
  const [rid, setRid] = useState("");
  const [name, setName] = useState("");
  const [slot1, setSlot1] = useState("slot-1");
  const [slot2, setSlot2] = useState("slot-2");

  const reload = async () => {
    const [cfg, alive] = await Promise.all([listRepeaterConfigs(), listRepeaters()]);
    setRows(cfg);
    setLive(alive);
  };
  useEffect(() => {
    if (open) reload();
  }, [open]);

  const chNameOf = (id) => channels.find((c) => c.id === id)?.name || id;

  const save = async () => {
    if (!rid) return toast.error("Repeater ID required");
    try {
      await upsertRepeaterConfig(parseInt(rid, 10), {
        name: name || `MMDVM ${rid}`,
        slot1_channel_id: slot1,
        slot2_channel_id: slot2,
      });
      toast.success("Saved");
      setRid("");
      setName("");
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    }
  };

  const remove = async (id) => {
    if (!window.confirm(`Delete config for MMDVM ${id}?`)) return;
    await deleteRepeaterConfig(id);
    reload();
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose?.()}>
      <DialogContent
        data-testid="repeater-config-modal"
        className="max-w-3xl bg-[#0a0a0a] border-[#2a2a2a] text-neutral-100 rounded-none p-0"
      >
        <DialogHeader className="border-b border-[#2a2a2a] p-4">
          <DialogTitle className="text-base flex items-center gap-2">
            <Server className="h-4 w-4" /> MMDVM Channel Bindings
          </DialogTitle>
          <DialogDescription className="mono text-[10px] text-neutral-500">
            For every MMDVM you plan to connect, pick which channel is on
            timeslot 1 and which is on timeslot 2. Voice frames are relayed
            only between MMDVMs that share a channel (the slot bit is rewritten
            automatically if a channel sits on a different slot on the target
            MMDVM).
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-[1fr_1fr] gap-0">
          {/* left - existing */}
          <div className="border-r border-[#2a2a2a] p-3">
            <div className="mono mb-2 text-[10px] uppercase tracking-widest text-neutral-500">
              Configured ({rows.length})
            </div>
            {rows.length === 0 && (
              <div className="mono text-[10px] text-neutral-600">
                No repeaters configured yet.
              </div>
            )}
            <div className="space-y-1">
              {rows.map((r) => {
                const alive = live.find((l) => l.repeater_id === r.repeater_id);
                return (
                  <div
                    key={r.repeater_id}
                    data-testid={`rc-row-${r.repeater_id}`}
                    className="border border-[#2a2a2a] p-2 mono text-[11px]"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-neutral-100">
                          {r.name}
                        </span>{" "}
                        <span className="text-neutral-500">#{r.repeater_id}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {alive && alive.authenticated && (
                          <span className="text-[9px] text-[#39ff14]">LIVE</span>
                        )}
                        <button
                          data-testid={`rc-delete-${r.repeater_id}`}
                          onClick={() => remove(r.repeater_id)}
                          className="text-neutral-500 hover:text-[#ff3b30]"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </div>
                    <div className="text-[10px] text-neutral-500">
                      TS1: {chNameOf(r.slot1_channel_id)} · TS2:{" "}
                      {chNameOf(r.slot2_channel_id)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* right - add / edit */}
          <div className="p-3 space-y-2">
            <div className="mono mb-1 text-[10px] uppercase tracking-widest text-neutral-500">
              Add / update
            </div>
            <input
              data-testid="rc-form-rid"
              value={rid}
              onChange={(e) => setRid(e.target.value)}
              placeholder="Repeater ID (7 digits)"
              className="w-full border border-[#2a2a2a] bg-black px-2 py-1 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
            />
            <input
              data-testid="rc-form-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Nickname (e.g. NorCal-1)"
              className="w-full border border-[#2a2a2a] bg-black px-2 py-1 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
            />
            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                <span className="mono block text-[10px] uppercase tracking-widest text-neutral-500">
                  TS1 →
                </span>
                <select
                  data-testid="rc-form-slot1"
                  value={slot1}
                  onChange={(e) => setSlot1(e.target.value)}
                  className="w-full border border-[#2a2a2a] bg-black px-2 py-1 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
                >
                  {channels.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mono block text-[10px] uppercase tracking-widest text-neutral-500">
                  TS2 →
                </span>
                <select
                  data-testid="rc-form-slot2"
                  value={slot2}
                  onChange={(e) => setSlot2(e.target.value)}
                  className="w-full border border-[#2a2a2a] bg-black px-2 py-1 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
                >
                  {channels.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </label>
            </div>
            <button
              data-testid="rc-form-save"
              onClick={save}
              className="flex w-full items-center justify-center gap-1 border border-[#39ff14] bg-[#0a1a0a] px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14] hover:text-black"
            >
              <Save className="h-3 w-3" /> Save Binding
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
