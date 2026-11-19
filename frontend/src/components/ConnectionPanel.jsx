import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Globe, RotateCw, Save, Wifi } from "lucide-react";
import { detectPublicIp, getConnection, restartServer, saveConnection } from "@/lib/api";

const input = "w-full border border-[#2a2a2a] bg-black px-2 py-1 text-neutral-100 outline-none focus:border-[#00f0ff]";
const errMsg = (e) => e?.response?.data?.detail?.[0]?.msg || e?.response?.data?.detail || e.message;

function F({ label, hint, children }) {
  return (
    <label className="block space-y-0.5">
      <span className="text-[9px] uppercase tracking-[0.25em] text-neutral-500">{label}</span>
      {children}
      {hint && <span className="block text-[9px] text-neutral-600">{hint}</span>}
    </label>
  );
}

// Server-side settings MMDVMs need. Saved now, applied on next restart.
export function ConnectionPanel({ onLoaded }) {
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const d = await getConnection();
    setInfo(d);
    setForm(d.saved);
    onLoaded?.(d);
  };
  useEffect(() => {
    load().catch(() => toast.error("Couldn't load connection settings"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!form) return <div className="px-3 pb-3 mono text-[11px] text-neutral-500">// loading…</div>;

  const set = (k, num) => (e) => setForm({ ...form, [k]: num ? Number(e.target.value) : e.target.value });
  const save = async () => {
    setBusy(true);
    try {
      const d = await saveConnection(form);
      setInfo(d);
      onLoaded?.(d);
      toast.success(d.pending_restart ? "Saved - applies after the next restart" : "Saved");
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  const detect = async () => {
    try {
      const { ip } = await detectPublicIp();
      setForm({ ...form, public_host: ip });
      toast.success(`Public IP ${ip} - press Save to keep it`);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const restart = async () => {
    if (!window.confirm("Restart the server now? Live screens reconnect in about 10 seconds.")) return;
    await restartServer();
    toast("Restarting…");
    setTimeout(() => window.location.reload(), 8000);
  };

  return (
    <div data-testid="connection-panel" className="space-y-2 px-3 pb-3 mono text-[11px] text-neutral-300">
      <div data-testid="connection-local-ips" className="flex flex-wrap items-center gap-1">
        <Wifi className="h-3.5 w-3.5 text-neutral-500" />
        <span className="text-neutral-500">This computer ({info.hostname}):</span>
        {info.local_ips.map((ip) => (
          <span key={ip} className="border border-[#2a2a2a] px-1.5 text-neutral-100">{ip}</span>
        ))}
        <span className={info.listening ? "text-[#39ff14]" : "text-[#ff3b30]"}>
          · {info.listening ? `listening on UDP ${info.running.hb_port}` : "NOT listening - port in use?"}
        </span>
      </div>
      <F label="Public address (domain or global IP) for MMDVMs outside your network" hint="Remote MMDVMs use this. Forward UDP port below to this computer on your router, or use the hosted server.">
        <div className="flex gap-1">
          <input data-testid="conn-public-host" value={form.public_host} onChange={set("public_host")} placeholder="dmr.yourclub.org or 81.2.3.4" className={input} />
          <button data-testid="conn-detect-ip" onClick={detect} title="Detect public IP" className="border border-[#2a2a2a] px-2 text-neutral-300 hover:border-[#00f0ff] hover:text-[#00f0ff]">
            <Globe className="h-3.5 w-3.5" />
          </button>
        </div>
      </F>
      <F label="Local address for MMDVMs on your network (optional)" hint={`Leave blank to use ${info.local_ips[0] || "this computer's IP"}.`}>
        <input data-testid="conn-local-host" value={form.local_host} onChange={set("local_host")} placeholder={info.local_ips[0] || "192.168.1.50"} className={input} />
      </F>
      <div className="grid grid-cols-2 gap-2">
        <F label="UDP port">
          <input data-testid="conn-port" type="number" value={form.hb_port} onChange={set("hb_port", true)} className={input} />
        </F>
        <F label="Server DMR ID" hint="Dispatcher calls/texts come from this ID">
          <input data-testid="conn-server-id" type="number" value={form.server_dmr_id} onChange={set("server_dmr_id", true)} className={input} />
        </F>
        <F label="Colour code">
          <input data-testid="conn-cc" type="number" min="0" max="15" value={form.color_code} onChange={set("color_code", true)} className={input} />
        </F>
        <F label="Shared password" hint={info.per_mmdvm_passwords ? "Not used - MMDVMs have their own passwords" : "Used until you add MMDVMs below"}>
          <input data-testid="conn-shared-password" value={form.shared_password} onChange={set("shared_password")} className={input} />
        </F>
        <F label="Voice timeslot">
          <select data-testid="conn-voice-slot" value={form.voice_slot} onChange={set("voice_slot", true)} className={input}>
            <option value={1}>TS1</option>
            <option value={2}>TS2</option>
          </select>
        </F>
        <F label="GPS / text timeslot">
          <select data-testid="conn-data-slot" value={form.data_slot} onChange={set("data_slot", true)} className={input}>
            <option value={1}>TS1</option>
            <option value={2}>TS2</option>
          </select>
        </F>
      </div>
      {info.pending_restart && (
        <div data-testid="connection-pending" className="flex items-center justify-between gap-2 border border-[#ffb800] bg-[#1a1005] px-2 py-1.5 text-[#ffb800]">
          Saved changes apply after the next restart.
          <button data-testid="conn-restart" onClick={restart} className="flex items-center gap-1 border border-[#ffb800] px-2 py-0.5 uppercase hover:bg-[#ffb800] hover:text-black">
            <RotateCw className="h-3 w-3" /> Restart now
          </button>
        </div>
      )}
      <button data-testid="conn-save" onClick={save} disabled={busy} className="flex items-center gap-1 border border-[#00f0ff] px-3 py-1 uppercase tracking-widest text-[#00f0ff] hover:bg-[#00f0ff] hover:text-black disabled:opacity-40">
        <Save className="h-3 w-3" /> Save
      </button>
    </div>
  );
}
