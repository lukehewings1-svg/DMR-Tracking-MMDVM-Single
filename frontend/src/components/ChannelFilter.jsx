import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Radio, Save, Settings2 } from "lucide-react";
import { updateChannel } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

/**
 * Channel filter chips + admin rename modal.
 * `filter` is null | 1 | 2. Clicking a chip toggles it as the current filter.
 */
export function ChannelFilter({ channels, filter, onFilter, onChanged }) {
  const { user } = useAuth();
  const [editing, setEditing] = useState(null); // channel object being renamed
  const isAdmin = user?.role === "admin";

  return (
    <div className="border-b border-[#2a2a2a] p-3" data-testid="channel-filter">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">
          Channels (Timeslots)
        </div>
      </div>
      <div className="flex flex-wrap gap-1" data-testid="channel-chips">
        <Chip
          testid="channel-chip-all"
          label="ALL"
          active={!filter}
          onClick={() => onFilter?.(null)}
        />
        {channels.map((c) => {
          // channel filter still uses last_channel (1|2) which reflects the
          // physical timeslot the packet came in on. Legacy slot-1/slot-2
          // channels map directly; user-added channels currently share the
          // slot the source MMDVM has bound them to at ingest time.
          const slot = c.id === "slot-2" ? 2 : 1;
          return (
            <div key={c.id} className="flex">
              <Chip
                testid={`channel-chip-${c.id}`}
                icon={<Radio className="h-3 w-3" />}
                label={c.name || c.id}
                color={c.color}
                active={filter === slot}
                onClick={() => onFilter?.(filter === slot ? null : slot)}
              />
              {isAdmin && (
                <button
                  data-testid={`channel-edit-${c.id}`}
                  onClick={() => setEditing(c)}
                  className="ml-[-1px] border border-[#2a2a2a] px-1.5 text-neutral-500 hover:border-[#00f0ff] hover:text-[#00f0ff]"
                  title="Rename channel"
                >
                  <Settings2 className="h-3 w-3" />
                </button>
              )}
            </div>
          );
        })}
      </div>

      <ChannelEditModal
        channel={editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          onChanged?.();
        }}
      />
    </div>
  );
}

function Chip({ label, active, onClick, color, icon, hint, testid }) {
  const c = color || "#39ff14";
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className={`flex items-center gap-1.5 border px-2 py-1 mono text-[10px] uppercase tracking-wider transition-colors ${
        active ? "" : "bg-transparent text-neutral-400 hover:text-neutral-100"
      }`}
      style={
        active
          ? { borderColor: c, backgroundColor: c, color: "#000" }
          : { borderColor: color ? c + "55" : "#2a2a2a" }
      }
    >
      {icon}
      <span>{label}</span>
      {hint && (
        <span className={active ? "opacity-70" : "text-neutral-500"}>{hint}</span>
      )}
    </button>
  );
}

function ChannelEditModal({ channel, onClose, onSaved }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  // rehydrate when a channel opens
  if (channel && name === "" && description === "" && channel.name !== name) {
    // no-op: guard against stale state; user typing preserved once they touch fields
  }

  const open = !!channel;
  const save = async () => {
    try {
      await updateChannel(channel.id, {
        name: name || channel.name,
        description: description || channel.description,
      });
      toast.success("Channel renamed");
      onSaved?.();
      setName("");
      setDescription("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          onClose?.();
          setName("");
          setDescription("");
        }
      }}
    >
      <DialogContent
        data-testid="channel-edit-modal"
        className="max-w-md bg-[#0a0a0a] border-[#2a2a2a] text-neutral-100 rounded-none p-0"
      >
        <DialogHeader className="border-b border-[#2a2a2a] p-4">
          <DialogTitle className="text-base">
            Rename Channel
          </DialogTitle>
          <DialogDescription className="mono text-[10px] text-neutral-500">
            Label for channel {channel?.name}. Radios and dispatchers see this
            name across the app.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 p-4">
          <label className="block">
            <span className="mono mb-1 block text-[10px] uppercase tracking-widest text-neutral-500">
              Name
            </span>
            <input
              data-testid="channel-edit-name"
              autoFocus
              defaultValue={channel?.name || ""}
              onChange={(e) => setName(e.target.value)}
              className="w-full border border-[#2a2a2a] bg-black px-3 py-2 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
            />
          </label>
          <label className="block">
            <span className="mono mb-1 block text-[10px] uppercase tracking-widest text-neutral-500">
              Description
            </span>
            <textarea
              data-testid="channel-edit-desc"
              rows={2}
              defaultValue={channel?.description || ""}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full border border-[#2a2a2a] bg-black px-3 py-2 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
            />
          </label>
          <button
            data-testid="channel-edit-save"
            onClick={save}
            className="flex w-full items-center justify-center gap-1.5 border border-[#39ff14] bg-[#0a1a0a] px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14] hover:text-black"
          >
            <Save className="h-3 w-3" /> Save
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
