import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ChevronDown, ChevronRight, Copy, Eye, EyeOff, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { addMmdvm, deleteMmdvm, listMmdvms, updateMmdvm } from "@/lib/api";

const input = "w-full border border-[#2a2a2a] bg-black px-2 py-1 text-neutral-100 outline-none focus:border-[#00f0ff]";
const errMsg = (e) => e?.response?.data?.detail?.[0]?.msg || e?.response?.data?.detail || e.message;
const newPassword = () => Array.from(crypto.getRandomValues(new Uint8Array(9)), (b) => "abcdefghjkmnpqrstuvwxyz23456789"[b % 31]).join("");
const copy = (text) => navigator.clipboard?.writeText(text).then(() => toast.success("Copied"));

function SetupInfo({ m, conn }) {
  const local = conn?.saved.local_host || conn?.local_ips?.[0] || "this-computer-ip";
  const remote = conn?.saved.public_host;
  const port = conn?.running.hb_port;
  const ini = `[DMR Network]\nEnable=1\nType=Direct\nRemoteAddress=${remote || local}\nRemotePort=${port}\nLocalPort=62032\nPassword=${m.password}\nSlot1=1\nSlot2=1\n`;
  const Row = ({ k, v }) => (
    <div className="grid grid-cols-[120px_1fr_auto] items-center gap-2">
      <span className="text-neutral-500">{k}</span>
      <span className="break-all text-neutral-100">{v}</span>
      <button onClick={() => copy(String(v))} className="text-neutral-500 hover:text-[#00f0ff]"><Copy className="h-3 w-3" /></button>
    </div>
  );
  return (
    <div data-testid={`mmdvm-setup-${m.id}`} className="space-y-1 border-t border-[#2a2a2a] bg-black/60 p-2">
      <div className="text-[9px] uppercase tracking-[0.25em] text-neutral-500">Pi-Star → Configuration → Expert → DMR Network</div>
      <Row k="Address (on site)" v={local} />
      <Row k="Address (remote)" v={remote || "set a public address above"} />
      <Row k="Port" v={port} />
      <Row k="Password" v={m.password} />
      <Row k="Local port" v="62032" />
      <Row k="DMR / repeater ID" v={m.repeater_id} />
      <div className="flex items-center justify-between pt-1">
        <span className="text-[9px] uppercase tracking-[0.25em] text-neutral-500">MMDVMHost.ini</span>
        <button data-testid={`mmdvm-copy-ini-${m.id}`} onClick={() => copy(ini)} className="flex items-center gap-1 text-neutral-400 hover:text-[#00f0ff]"><Copy className="h-3 w-3" /> copy</button>
      </div>
      <pre className="overflow-x-auto whitespace-pre text-[10px] text-neutral-300">{ini}</pre>
    </div>
  );
}

function MmdvmForm({ initial, onSave, onCancel }) {
  const [f, setF] = useState(initial);
  return (
    <div data-testid="mmdvm-form" className="space-y-1.5 border border-[#00f0ff]/50 p-2">
      <input data-testid="mmdvm-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Name, e.g. North hill repeater" className={input} />
      <input data-testid="mmdvm-id" type="number" value={f.repeater_id} onChange={(e) => setF({ ...f, repeater_id: e.target.value })} placeholder="MMDVM ID (Pi-Star DMR ID + 2 digits, e.g. 234567801)" className={input} />
      <div className="flex gap-1">
        <input data-testid="mmdvm-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} placeholder="Password" className={input} />
        <button onClick={() => setF({ ...f, password: newPassword() })} title="Generate" className="border border-[#2a2a2a] px-2 text-neutral-400 hover:text-[#00f0ff]"><RefreshCw className="h-3 w-3" /></button>
      </div>
      <div className="flex gap-2">
        <button data-testid="mmdvm-save" onClick={() => onSave({ ...f, repeater_id: Number(f.repeater_id) })} className="border border-[#00f0ff] px-3 py-1 uppercase tracking-widest text-[#00f0ff] hover:bg-[#00f0ff] hover:text-black">Save</button>
        <button onClick={onCancel} className="px-2 text-neutral-500 hover:text-neutral-200">Cancel</button>
      </div>
    </div>
  );
}

export function MmdvmsPanel({ conn, repeaters }) {
  const [items, setItems] = useState([]);
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(null);
  const [shown, setShown] = useState({});
  const online = new Set((repeaters || []).filter((r) => r.authenticated).map((r) => r.repeater_id));
  const reload = () => listMmdvms().then(setItems).catch(() => {});
  useEffect(() => {
    reload();
  }, []);

  const save = async (f) => {
    try {
      if (f.id) await updateMmdvm(f.id, { name: f.name, repeater_id: f.repeater_id, password: f.password, notes: f.notes || null });
      else await addMmdvm({ name: f.name, repeater_id: f.repeater_id, password: f.password });
      setEditing(null);
      toast.success("Saved - takes effect immediately");
      reload();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const remove = async (m) => {
    if (!window.confirm(`Remove ${m.name}? It will no longer be able to connect.`)) return;
    try {
      await deleteMmdvm(m.id);
      reload();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const rejected = conn?.rejected_logins || [];

  return (
    <div data-testid="mmdvms-panel" className="space-y-2 px-3 pb-3 mono text-[11px] text-neutral-300">
      <div className="text-neutral-500">
        {items.length ? "Only the MMDVMs listed here can connect, each with its own password." : "No MMDVMs added yet - any MMDVM with the shared password can connect. Add one to switch to per-MMDVM passwords."}
      </div>
      {items.map((m) =>
        editing?.id === m.id ? (
          <MmdvmForm key={m.id} initial={m} onSave={save} onCancel={() => setEditing(null)} />
        ) : (
          <div key={m.id} data-testid={`mmdvm-row-${m.id}`} className="border border-[#2a2a2a]">
            <div className="flex items-center gap-2 px-2 py-1.5">
              <button onClick={() => setOpen(open === m.id ? null : m.id)} data-testid={`mmdvm-toggle-${m.id}`} className="text-neutral-500">
                {open === m.id ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              </button>
              <span className={`h-2 w-2 ${online.has(m.repeater_id) ? "bg-[#39ff14]" : "bg-neutral-600"}`} title={online.has(m.repeater_id) ? "connected" : "offline"} />
              <span className="flex-1 truncate text-neutral-100">{m.name}</span>
              <span className="text-neutral-500">{m.repeater_id}</span>
              <span className="w-20 truncate text-right text-neutral-400">{shown[m.id] ? m.password : "••••••"}</span>
              <button onClick={() => setShown({ ...shown, [m.id]: !shown[m.id] })} className="text-neutral-500 hover:text-neutral-200">{shown[m.id] ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}</button>
              <button data-testid={`mmdvm-edit-${m.id}`} onClick={() => setEditing(m)} className="text-neutral-500 hover:text-[#00f0ff]"><Pencil className="h-3 w-3" /></button>
              <button data-testid={`mmdvm-delete-${m.id}`} onClick={() => remove(m)} className="text-neutral-500 hover:text-[#ff3b30]"><Trash2 className="h-3 w-3" /></button>
            </div>
            {open === m.id && <SetupInfo m={m} conn={conn} />}
          </div>
        ),
      )}
      {editing && !editing.id ? (
        <MmdvmForm initial={editing} onSave={save} onCancel={() => setEditing(null)} />
      ) : (
        <button data-testid="mmdvm-add" onClick={() => setEditing({ name: "", repeater_id: "", password: newPassword() })} className="flex items-center gap-1 border border-[#00f0ff] px-2 py-1 uppercase tracking-widest text-[#00f0ff] hover:bg-[#00f0ff] hover:text-black">
          <Plus className="h-3 w-3" /> Add MMDVM
        </button>
      )}
      {rejected.length > 0 && (
        <div data-testid="mmdvm-rejected" className="space-y-1 border border-[#ff3b30]/50 p-2">
          <div className="text-[9px] uppercase tracking-[0.25em] text-[#ff3b30]">Recently refused logins</div>
          {rejected.map((r) => (
            <div key={r.repeater_id} className="flex items-center gap-2">
              <span className="text-neutral-100">{r.repeater_id}</span>
              <span className="text-neutral-500">{r.ip} · {r.reason}</span>
              {!items.some((m) => m.repeater_id === r.repeater_id) && (
                <button data-testid={`mmdvm-add-rejected-${r.repeater_id}`} onClick={() => setEditing({ name: "", repeater_id: r.repeater_id, password: newPassword() })} className="ml-auto text-[#00f0ff] hover:underline">add</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
