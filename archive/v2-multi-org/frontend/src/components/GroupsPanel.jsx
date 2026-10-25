import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { createGroup, updateGroup, deleteGroup, simulateEmergency } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2, Save, X, Radio, AlertOctagon } from "lucide-react";
import { ICON_SET, COLOR_SET, iconFor } from "@/lib/icons";
import { useAuth } from "@/context/AuthContext";

export function GroupsPanel({ groups, filter, onFilter, onChanged, embedded }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin" || user?.role === "super_admin";
  const [open, setOpen] = useState(false);

  return (
    <div className={embedded ? "px-3 pb-2" : "border-b border-[#2a2a2a] p-3"} data-testid="groups-panel">
      {(!embedded || isAdmin) && (
        <div className="mb-2 flex items-center justify-between">
          {!embedded && (
            <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">
              Groups (Talk Groups)
            </div>
          )}
          {embedded && <div />}
          {isAdmin && (
            <button
              data-testid="groups-manage"
              onClick={() => setOpen(true)}
              className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-0.5 mono text-[10px] uppercase text-neutral-400 hover:border-[#00f0ff] hover:text-[#00f0ff]"
            >
              <Plus className="h-3 w-3" /> Manage
            </button>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-1" data-testid="group-filter-chips">
        <FilterChip
          label="ALL"
          active={!filter}
          onClick={() => onFilter?.(null)}
          testid="group-chip-all"
        />
        {groups.map((g) => {
          const IconC = iconFor(g.icon);
          return (
            <FilterChip
              key={g.id}
              testid={`group-chip-${g.id}`}
              label={g.name}
              tg={g.talkgroup_id}
              color={g.color}
              icon={<IconC className="h-3 w-3" />}
              active={filter === g.id}
              onClick={() => onFilter?.(filter === g.id ? null : g.id)}
            />
          );
        })}
      </div>

      <GroupsManagerModal
        open={open}
        onClose={() => setOpen(false)}
        groups={groups}
        onChanged={onChanged}
      />
    </div>
  );
}

function FilterChip({ label, active, onClick, color, icon, tg, testid }) {
  const c = color || "#39ff14";
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className={`flex items-center gap-1.5 border px-2 py-1 mono text-[10px] uppercase tracking-wider transition-colors ${
        active
          ? "bg-black text-black"
          : "bg-transparent text-neutral-400 hover:text-neutral-100"
      }`}
      style={
        active
          ? { borderColor: c, backgroundColor: c, color: "#000" }
          : { borderColor: color ? c + "55" : "#2a2a2a" }
      }
    >
      {icon}
      <span>{label}</span>
      {tg != null && (
        <span className={`opacity-70 ${active ? "" : "text-neutral-500"}`}>
          TG{tg}
        </span>
      )}
    </button>
  );
}

function GroupsManagerModal({ open, onClose, groups, onChanged }) {
  const [editing, setEditing] = useState(null); // group id or "new"
  const [draft, setDraft] = useState(defaultDraft());

  function defaultDraft() {
    return { name: "", talkgroup_id: 91, color: "#39ff14", icon: "Users", description: "" };
  }

  const startNew = () => {
    setEditing("new");
    setDraft(defaultDraft());
  };
  const startEdit = (g) => {
    setEditing(g.id);
    setDraft({
      name: g.name,
      talkgroup_id: g.talkgroup_id,
      color: g.color || "#39ff14",
      icon: g.icon || "Users",
      description: g.description || "",
    });
  };
  const cancel = () => {
    setEditing(null);
    setDraft(defaultDraft());
  };

  const save = async () => {
    try {
      if (editing === "new") {
        await createGroup(draft);
        toast.success("Group created");
      } else {
        await updateGroup(editing, draft);
        toast.success("Group updated");
      }
      cancel();
      onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this group? Radios in it will be unassigned.")) return;
    await deleteGroup(id);
    toast.success("Group deleted");
    onChanged?.();
  };

  const IconComp = iconFor(draft.icon);

  return (
    <Dialog open={open} onOpenChange={(v) => !v && (onClose?.(), cancel())}>
      <DialogContent
        data-testid="groups-manager"
        className="max-w-3xl bg-[#0a0a0a] border-[#2a2a2a] text-neutral-100 rounded-none p-0"
      >
        <DialogHeader className="border-b border-[#2a2a2a] p-4">
          <DialogTitle className="text-base">Manage Groups (Talk Groups)</DialogTitle>
          <DialogDescription className="mono text-[10px] text-neutral-500">
            Create, rename, recolor or delete talk groups. Radios are auto-assigned to a group
            the first time they transmit on its DMR talkgroup ID.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-[1fr_1.2fr] gap-0">
          {/* left: list */}
          <div className="border-r border-[#2a2a2a]">
            <div className="flex items-center justify-between border-b border-[#2a2a2a] px-3 py-2">
              <span className="text-[10px] uppercase tracking-widest text-neutral-500">
                {groups.length} groups
              </span>
              <button
                data-testid="groups-new"
                onClick={startNew}
                className="flex items-center gap-1 border border-[#39ff14] px-2 py-0.5 mono text-[10px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14] hover:text-black"
              >
                <Plus className="h-3 w-3" /> New
              </button>
            </div>
            <div className="max-h-[420px] overflow-y-auto">
              {groups.map((g) => {
                const IC = iconFor(g.icon);
                return (
                  <div
                    key={g.id}
                    data-testid={`group-row-${g.id}`}
                    className={`flex items-center justify-between border-b border-[#1a1a1a] px-3 py-2 cursor-pointer ${
                      editing === g.id ? "bg-[#001a1f]" : "hover:bg-[#111]"
                    }`}
                    onClick={() => startEdit(g)}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <div
                        className="flex h-6 w-6 items-center justify-center border shrink-0"
                        style={{ color: g.color, borderColor: g.color + "55" }}
                      >
                        <IC className="h-3.5 w-3.5" />
                      </div>
                      <div className="min-w-0">
                        <div className="mono text-sm text-neutral-100 truncate">
                          {g.name}
                        </div>
                        <div className="mono text-[10px] text-neutral-500">
                          TG {g.talkgroup_id}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        data-testid={`group-simulate-emg-${g.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          simulateEmergency({
                            dmr_id: 9999000 + g.talkgroup_id,
                            talkgroup_id: g.talkgroup_id,
                          }).then(() => toast.success("Test emergency fired"));
                        }}
                        className="border border-[#2a2a2a] p-1 text-neutral-500 hover:border-[#ff3b30] hover:text-[#ff3b30]"
                        title="Simulate emergency on this TG"
                      >
                        <AlertOctagon className="h-3 w-3" />
                      </button>
                      <button
                        data-testid={`group-delete-${g.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          remove(g.id);
                        }}
                        className="border border-[#2a2a2a] p-1 text-neutral-500 hover:border-[#ff3b30] hover:text-[#ff3b30]"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* right: editor */}
          <div className="p-4">
            {!editing ? (
              <div className="mono text-[11px] text-neutral-500">
                Select a group on the left, or click <span className="text-[#39ff14]">+ New</span>.
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <div
                    className="flex h-10 w-10 items-center justify-center border"
                    style={{ color: draft.color, borderColor: draft.color + "60" }}
                  >
                    <IconComp className="h-5 w-5" />
                  </div>
                  <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                    {editing === "new" ? "New Group" : "Edit Group"}
                  </div>
                </div>

                <Field label="Name">
                  <input
                    data-testid="group-form-name"
                    value={draft.name}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                    className="w-full border border-[#2a2a2a] bg-black px-2 py-1 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
                  />
                </Field>
                <Field label="Talkgroup ID">
                  <input
                    data-testid="group-form-tg"
                    type="number"
                    value={draft.talkgroup_id}
                    onChange={(e) =>
                      setDraft({ ...draft, talkgroup_id: parseInt(e.target.value, 10) || 0 })
                    }
                    className="w-full border border-[#2a2a2a] bg-black px-2 py-1 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
                  />
                </Field>
                <Field label="Description">
                  <input
                    data-testid="group-form-desc"
                    value={draft.description}
                    onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                    className="w-full border border-[#2a2a2a] bg-black px-2 py-1 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
                  />
                </Field>
                <div>
                  <div className="mono mb-1 text-[10px] uppercase tracking-widest text-neutral-500">
                    Icon
                  </div>
                  <div className="grid grid-cols-9 gap-1">
                    {ICON_SET.map(({ key, Icon }) => (
                      <button
                        key={key}
                        data-testid={`group-form-icon-${key}`}
                        type="button"
                        onClick={() => setDraft({ ...draft, icon: key })}
                        className={`flex aspect-square items-center justify-center border transition-colors ${
                          draft.icon === key
                            ? "border-[#00f0ff] bg-[#001a1f] text-[#00f0ff]"
                            : "border-[#2a2a2a] text-neutral-400 hover:text-neutral-100"
                        }`}
                      >
                        <Icon className="h-3.5 w-3.5" />
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="mono mb-1 text-[10px] uppercase tracking-widest text-neutral-500">
                    Color
                  </div>
                  <div className="flex gap-1.5">
                    {COLOR_SET.map(({ key, label }) => (
                      <button
                        key={key}
                        data-testid={`group-form-color-${label.toLowerCase()}`}
                        type="button"
                        onClick={() => setDraft({ ...draft, color: key })}
                        className={`h-6 w-6 border transition-transform ${
                          draft.color === key
                            ? "scale-110 border-white"
                            : "border-[#2a2a2a] hover:scale-105"
                        }`}
                        style={{ background: key }}
                      />
                    ))}
                  </div>
                </div>
                <div className="flex gap-2 pt-2">
                  <button
                    data-testid="group-form-save"
                    onClick={save}
                    className="flex items-center gap-1 border border-[#39ff14] bg-[#0a1a0a] px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14] hover:text-black"
                  >
                    <Save className="h-3 w-3" /> Save
                  </button>
                  <button
                    data-testid="group-form-cancel"
                    onClick={cancel}
                    className="flex items-center gap-1 border border-[#2a2a2a] px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-neutral-400 hover:border-neutral-500 hover:text-neutral-100"
                  >
                    <X className="h-3 w-3" /> Cancel
                  </button>
                </div>
              </div>
            )}
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
