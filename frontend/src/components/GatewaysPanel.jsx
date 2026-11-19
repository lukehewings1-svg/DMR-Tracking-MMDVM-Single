import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy, Plus, Trash2 } from "lucide-react";
import { createGateway, deleteGateway, listGateways, voiceStatus } from "@/lib/api";

export function GatewaysPanel() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState(null);
  const [name, setName] = useState("");
  const [newKey, setNewKey] = useState(null);

  const refresh = () => {
    listGateways().then(setItems).catch(() => {});
    voiceStatus().then(setStatus).catch(() => {});
  };
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10000);
    return () => clearInterval(t);
  }, []);

  const add = async () => {
    if (!name.trim()) return;
    const g = await createGateway(name.trim());
    setNewKey(g);
    setName("");
    refresh();
  };
  const remove = async (g) => {
    if (!window.confirm(`Remove gateway "${g.name}"? It will be disconnected.`)) return;
    await deleteGateway(g.id);
    refresh();
  };
  const d = status?.dongle;

  return (
    <div data-testid="gateways-panel" className="space-y-2 px-3 pb-3 mono text-[11px] text-neutral-300">
      <div data-testid="voice-dongle-status" className="border border-[#2a2a2a] px-2 py-1.5">
        AMBE dongle:{" "}
        {d?.ok ? (
          <span className="text-[#39ff14]">connected · {d.product} ({d.path})</span>
        ) : d?.configured ? (
          <span className="text-[#ff3b30]">{d.error}</span>
        ) : (
          <span className="text-neutral-500">not configured (set AMBE_DEVICE_PATH in backend/.env)</span>
        )}
        <div className="text-neutral-500">Voice route now: {status?.route || "none — PTT sends a text message"}</div>
      </div>
      {items.map((g) => (
        <div key={g.id} data-testid={`gateway-row-${g.id}`} className="flex items-center gap-2 border border-[#2a2a2a] px-2 py-1.5">
          <span className={`h-2 w-2 ${g.online ? "bg-[#39ff14]" : "bg-neutral-600"}`} />
          <span className="flex-1 truncate text-neutral-100">{g.name}</span>
          <span className="text-neutral-500">{g.online ? "online" : g.last_seen ? `seen ${new Date(g.last_seen).toLocaleString()}` : "never connected"}</span>
          <button data-testid={`gateway-delete-${g.id}`} onClick={() => remove(g)} className="text-neutral-500 hover:text-[#ff3b30]">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      {newKey && (
        <div data-testid="gateway-new-key" className="space-y-1 border border-[#39ff14] bg-[#0a1a0a] p-2">
          <div className="text-[#39ff14]">Key for “{newKey.name}” — copy it into the Pi's gateway config now. It won't be shown again.</div>
          <div className="flex items-center gap-2">
            <code className="flex-1 break-all text-neutral-100">{newKey.key}</code>
            <button
              data-testid="gateway-copy-key"
              onClick={() => navigator.clipboard?.writeText(newKey.key).then(() => toast.success("Copied"))}
              className="text-neutral-400 hover:text-[#00f0ff]"
            >
              <Copy className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
      <div className="flex gap-2">
        <input
          data-testid="gateway-name-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Control room DMR818"
          className="min-w-0 flex-1 border border-[#2a2a2a] bg-black px-2 py-1 text-neutral-100 outline-none focus:border-[#00f0ff]"
        />
        <button data-testid="gateway-add" onClick={add} className="flex items-center gap-1 border border-[#00f0ff] px-2 py-1 uppercase tracking-widest text-[#00f0ff] hover:bg-[#00f0ff] hover:text-black">
          <Plus className="h-3 w-3" /> Add
        </button>
      </div>
    </div>
  );
}
