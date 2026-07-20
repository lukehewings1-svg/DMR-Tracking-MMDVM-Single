import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { adminSetUserGroups } from "@/lib/api";
import { toast } from "sonner";
import { Save, ShieldCheck } from "lucide-react";

export function UserGroupsModal({ user, groups, onClose, onSaved }) {
  const [selected, setSelected] = useState(new Set());

  useEffect(() => {
    if (user) setSelected(new Set(user.allowed_group_ids || []));
  }, [user]);

  const toggle = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const save = async () => {
    try {
      await adminSetUserGroups(user.id, Array.from(selected));
      toast.success("Group access saved");
      onSaved?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    }
  };

  return (
    <Dialog open={!!user} onOpenChange={(v) => !v && onClose?.()}>
      <DialogContent
        data-testid="user-groups-modal"
        className="max-w-md bg-[#0a0a0a] border-[#2a2a2a] text-neutral-100 rounded-none p-0"
      >
        <DialogHeader className="border-b border-[#2a2a2a] p-4">
          <DialogTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="h-4 w-4 text-[#00f0ff]" /> Group Access
          </DialogTitle>
          <DialogDescription className="mono text-[10px] text-neutral-500">
            {user?.email} · If no groups are selected the dispatcher can see
            every group (default). Selecting any groups restricts them to only
            those groups for both viewing and sending messages.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-72 overflow-y-auto p-3 space-y-1">
          {groups.length === 0 && (
            <div className="mono text-[10px] text-neutral-600">
              No groups defined yet.
            </div>
          )}
          {groups.map((g) => {
            const checked = selected.has(g.id);
            return (
              <label
                key={g.id}
                data-testid={`user-group-toggle-${g.id}`}
                className={`flex cursor-pointer items-center justify-between border px-2 py-1.5 mono text-[11px] ${
                  checked
                    ? "border-[#00f0ff] bg-[#001a1f]"
                    : "border-[#2a2a2a] hover:bg-[#111]"
                }`}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(g.id)}
                    className="accent-[#00f0ff]"
                  />
                  <span
                    className="inline-block h-2 w-2"
                    style={{ background: g.color }}
                  />
                  <span className="text-neutral-100">{g.name}</span>
                </div>
                <span className="text-neutral-500">TG {g.talkgroup_id}</span>
              </label>
            );
          })}
        </div>

        <div className="border-t border-[#2a2a2a] p-3">
          <button
            data-testid="user-groups-save"
            onClick={save}
            className="flex w-full items-center justify-center gap-1.5 border border-[#39ff14] bg-[#0a1a0a] px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14] hover:text-black"
          >
            <Save className="h-3 w-3" /> Save Access
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
