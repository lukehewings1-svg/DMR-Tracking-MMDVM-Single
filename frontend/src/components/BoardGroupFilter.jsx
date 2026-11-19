import { Check } from "lucide-react";

export const UNASSIGNED = "__none__";

export function filterByGroups(radios, selected) {
  if (!selected.length) return radios;
  return radios.filter((r) => selected.includes(r.group_id || UNASSIGNED));
}

function Chip({ active, onClick, color, label, testid }) {
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className={`flex shrink-0 items-center gap-1 border px-2 py-0.5 uppercase tracking-widest transition-colors ${
        active ? "bg-[#001a1f] text-neutral-100" : "border-[#2a2a2a] text-neutral-500 hover:text-neutral-200"
      }`}
      style={active ? { borderColor: color || "#00f0ff" } : undefined}
    >
      {active && <Check className="h-3 w-3" style={{ color: color || "#00f0ff" }} />}
      {label}
    </button>
  );
}

// Empty selection = all talkgroups.
export function BoardGroupFilter({ groups, selected, onChange }) {
  const toggle = (id) =>
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  return (
    <div data-testid="board-group-filter" className="flex min-w-0 items-center gap-1 overflow-x-auto mono text-[10px]">
      <Chip testid="board-group-all" active={!selected.length} onClick={() => onChange([])} label="All talkgroups" />
      {groups.map((g) => (
        <Chip key={g.id} testid={`board-group-${g.id}`} active={selected.includes(g.id)} onClick={() => toggle(g.id)} color={g.color} label={g.name} />
      ))}
      <Chip testid="board-group-unassigned" active={selected.includes(UNASSIGNED)} onClick={() => toggle(UNASSIGNED)} label="No group" />
    </div>
  );
}
