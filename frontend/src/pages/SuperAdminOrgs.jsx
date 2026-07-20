import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  listOrgs,
  createOrg,
  updateOrg,
  rotateOrgHbPassword,
  bootstrapOrgAdmin,
  deleteOrg,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import {
  ArrowLeft,
  Plus,
  KeyRound,
  UserPlus,
  Trash2,
  RefreshCw,
  Copy,
  Radio,
  Shield,
} from "lucide-react";
import { OrgLinksPanel } from "@/components/OrgLinksPanel";
import { EventsPanel } from "@/components/EventsPanel";
import { isSuperAdmin } from "@/lib/api";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const OVERLAY_API = axios.create({ baseURL: `${BACKEND_URL}/api` });
OVERLAY_API.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export default function SuperAdminOrgs() {
  const { user } = useAuth();
  const [orgs, setOrgs] = useState([]);
  const [overlays, setOverlays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [bootstrapFor, setBootstrapFor] = useState(null);

  const load = async () => {
    try {
      const [list, ov] = await Promise.all([
        listOrgs(),
        OVERLAY_API.get("/overlays").then((r) => r.data).catch(() => []),
      ]);
      setOrgs(list);
      setOverlays(ov);
    } catch (e) {
      toast.error("Failed to load organizations");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const act = async (fn, msg) => {
    try {
      await fn();
      if (msg) toast.success(msg);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Action failed");
    }
  };

  return (
    <div className="h-screen bg-[#050505] text-neutral-100" data-testid="superadmin-orgs">
      <header className="flex items-center justify-between border-b border-[#2a2a2a] px-4 py-3">
        <div className="flex items-center gap-3">
          <Link
            data-testid="back-to-dashboard"
            to="/"
            className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 mono text-[11px] uppercase tracking-widest text-neutral-400 hover:border-[#00f0ff] hover:text-[#00f0ff]"
          >
            <ArrowLeft className="h-3 w-3" /> Dashboard
          </Link>
          <div>
            <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">
              Super Admin
            </div>
            <h1 className="text-lg font-semibold flex items-center gap-2">
              <Shield className="h-4 w-4 text-[#00f0ff]" /> Organizations
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-3 mono text-[11px] text-neutral-400">
          <span>Signed in as</span>
          <span className="text-neutral-100">{user?.email}</span>
        </div>
      </header>

      <div className="overflow-y-auto" style={{ maxHeight: "calc(100vh - 60px)" }}>
        <div className="border-b border-[#2a2a2a] bg-[#0a0a0a] px-4 py-3 flex items-center justify-between">
          <div className="mono text-[11px] uppercase tracking-widest text-neutral-500">
            {orgs.length} organization{orgs.length === 1 ? "" : "s"}
          </div>
          {isSuperAdmin(user) && (
            <button
              data-testid="new-org-btn"
              onClick={() => setShowNew(true)}
              className="flex items-center gap-2 border border-[#39ff14] bg-[#39ff14]/10 px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14]/20"
            >
              <Plus className="h-3 w-3" /> New Organization
            </button>
          )}
        </div>

        {loading && (
          <div className="p-10 text-center mono text-xs text-neutral-500">
            loading…
          </div>
        )}

        <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-3">
          {orgs.map((o) => (
            <OrgCard
              key={o.id}
              org={o}
              isSuper={isSuperAdmin(user)}
              onUpdate={(patch) =>
                act(() => updateOrg(o.id, patch), "Organization updated")
              }
              onRotate={() =>
                act(() => rotateOrgHbPassword(o.id), "HB password rotated")
              }
              onBootstrap={() => setBootstrapFor(o)}
              onDelete={() => {
                if (window.confirm(`Delete "${o.name}"? This is irreversible.`))
                  act(() => deleteOrg(o.id), "Organization deleted");
              }}
            />
          ))}
        </div>

        <OrgLinksPanel orgs={orgs} />
        <EventsPanel orgs={orgs} overlays={overlays} />
      </div>

      {showNew && (
        <NewOrgModal
          onClose={() => setShowNew(false)}
          onCreated={() => {
            setShowNew(false);
            load();
          }}
        />
      )}
      {bootstrapFor && (
        <BootstrapAdminModal
          org={bootstrapFor}
          onClose={() => setBootstrapFor(null)}
          onDone={() => {
            setBootstrapFor(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function OrgCard({ org, isSuper, onUpdate, onRotate, onBootstrap, onDelete }) {
  const [showPwd, setShowPwd] = useState(false);
  return (
    <div
      data-testid={`org-card-${org.id}`}
      className="border border-[#2a2a2a] bg-[#0a0a0a] p-3"
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="mono text-[10px] uppercase tracking-[0.3em] text-neutral-500">
            {org.slug}
          </div>
          <div className="text-base font-semibold">{org.name}</div>
        </div>
        {isSuper && (
          <div className="flex items-center gap-1">
            <button
              data-testid={`bootstrap-${org.id}`}
              title="Create first admin user"
              onClick={onBootstrap}
              className="border border-[#2a2a2a] p-1.5 text-neutral-400 hover:text-[#39ff14] hover:border-[#39ff14]"
            >
              <UserPlus className="h-3.5 w-3.5" />
            </button>
            <button
              data-testid={`delete-org-${org.id}`}
              title="Delete organization"
              onClick={onDelete}
              className="border border-[#2a2a2a] p-1.5 text-neutral-400 hover:text-[#ff3b30] hover:border-[#ff3b30]"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>

      <div className="mt-3 grid gap-2 mono text-[11px]">
        <div className="flex items-center gap-2">
          <Radio className="h-3 w-3 text-[#00f0ff]" />
          <span className="text-neutral-500">MMDVM server DMR ID:</span>
          <span className="text-neutral-200">{org.server_dmr_id}</span>
        </div>
        <div className="flex items-center gap-2">
          <KeyRound className="h-3 w-3 text-[#ffb800]" />
          <span className="text-neutral-500">HB password:</span>
          <button
            data-testid={`toggle-pwd-${org.id}`}
            onClick={() => setShowPwd((v) => !v)}
            className="text-neutral-200 hover:text-[#00f0ff]"
          >
            {showPwd ? org.hb_password : "•".repeat(Math.min(org.hb_password?.length || 8, 16))}
          </button>
          {showPwd && (
            <>
              <button
                title="Copy"
                onClick={() => {
                  navigator.clipboard.writeText(org.hb_password);
                  toast.success("Copied");
                }}
                className="text-neutral-500 hover:text-neutral-200"
              >
                <Copy className="h-3 w-3" />
              </button>
              {isSuper && (
                <button
                  data-testid={`rotate-${org.id}`}
                  title="Rotate password"
                  onClick={onRotate}
                  className="text-neutral-500 hover:text-[#ffb800]"
                >
                  <RefreshCw className="h-3 w-3" />
                </button>
              )}
            </>
          )}
        </div>
        <label className="flex items-center gap-2">
          <input
            data-testid={`ack-toggle-${org.id}`}
            type="checkbox"
            checked={!!org.user_can_ack_emergency}
            onChange={(e) => onUpdate({ user_can_ack_emergency: e.target.checked })}
          />
          <span className="text-neutral-400">Users can acknowledge emergencies</span>
        </label>
      </div>
    </div>
  );
}

function NewOrgModal({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [serverDmrId, setServerDmrId] = useState(9990001);
  const [ackToggle, setAckToggle] = useState(true);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await createOrg({
        name,
        server_dmr_id: Number(serverDmrId),
        user_can_ack_emergency: ackToggle,
      });
      toast.success("Organization created");
      onCreated();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to create");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/70">
      <form
        onSubmit={submit}
        data-testid="new-org-modal"
        className="w-[420px] border border-[#2a2a2a] bg-[#0a0a0a] p-4"
      >
        <div className="mono text-[10px] uppercase tracking-[0.3em] text-neutral-500">
          New Organization
        </div>
        <h2 className="mb-4 text-lg font-semibold">Create Organization</h2>
        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Name
        </label>
        <input
          data-testid="new-org-name"
          autoFocus
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mb-3 w-full border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-sm text-neutral-100 outline-none focus:border-[#39ff14]"
        />
        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Server DMR ID (for MMDVM master handshake)
        </label>
        <input
          data-testid="new-org-dmrid"
          type="number"
          value={serverDmrId}
          onChange={(e) => setServerDmrId(e.target.value)}
          className="mb-3 w-full border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-sm text-neutral-100 outline-none focus:border-[#39ff14]"
        />
        <label className="mb-3 flex items-center gap-2">
          <input
            type="checkbox"
            checked={ackToggle}
            onChange={(e) => setAckToggle(e.target.checked)}
          />
          <span className="text-sm text-neutral-300">
            Users (not just admins) can acknowledge emergencies
          </span>
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="border border-[#2a2a2a] px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-neutral-400 hover:text-neutral-200"
          >
            Cancel
          </button>
          <button
            data-testid="create-org-submit"
            type="submit"
            disabled={busy}
            className="border border-[#39ff14] bg-[#39ff14]/10 px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14]/20 disabled:opacity-50"
          >
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}

function BootstrapAdminModal({ org, onClose, onDone }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [callsign, setCallsign] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await bootstrapOrgAdmin(org.id, { email, password, callsign });
      toast.success(`Admin ${email} created for ${org.name}`);
      onDone();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/70">
      <form
        onSubmit={submit}
        data-testid="bootstrap-admin-modal"
        className="w-[420px] border border-[#2a2a2a] bg-[#0a0a0a] p-4"
      >
        <div className="mono text-[10px] uppercase tracking-[0.3em] text-neutral-500">
          Bootstrap Admin
        </div>
        <h2 className="mb-1 text-lg font-semibold">Create first admin for</h2>
        <div className="mb-4 mono text-sm text-[#00f0ff]">{org.name}</div>
        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Email
        </label>
        <input
          data-testid="bootstrap-email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mb-3 w-full border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-sm text-neutral-100 outline-none focus:border-[#39ff14]"
        />
        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Password (min 6)
        </label>
        <input
          data-testid="bootstrap-password"
          type="password"
          required
          minLength={6}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mb-3 w-full border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-sm text-neutral-100 outline-none focus:border-[#39ff14]"
        />
        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Callsign (optional)
        </label>
        <input
          data-testid="bootstrap-callsign"
          value={callsign}
          onChange={(e) => setCallsign(e.target.value)}
          className="mb-3 w-full border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-sm text-neutral-100 outline-none focus:border-[#39ff14]"
        />
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="border border-[#2a2a2a] px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-neutral-400 hover:text-neutral-200"
          >
            Cancel
          </button>
          <button
            data-testid="bootstrap-submit"
            type="submit"
            disabled={busy}
            className="border border-[#39ff14] bg-[#39ff14]/10 px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14]/20 disabled:opacity-50"
          >
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}
