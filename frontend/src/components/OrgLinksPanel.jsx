import { useEffect, useState } from "react";
import {
  listOrgLinks,
  createOrgLink,
  approveOrgLink,
  revokeOrgLink,
  deleteOrgLink,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Link as LinkIcon, Check, X, Trash2, ArrowRight, Plus, Shield } from "lucide-react";
import { isAdmin, isSuperAdmin } from "@/lib/api";

const SHARE_KEYS = ["radios", "positions", "messages", "voice", "overlays", "geofences", "emergencies"];

export function OrgLinksPanel({ orgs }) {
  const { user } = useAuth();
  const [links, setLinks] = useState([]);
  const [showNew, setShowNew] = useState(false);

  const load = async () => {
    try {
      setLinks(await listOrgLinks());
    } catch (e) {
      toast.error("Failed to load org links");
    }
  };

  useEffect(() => {
    if (isAdmin(user)) load();
  }, [user]);

  if (!isAdmin(user)) return null;

  const orgName = (id) => orgs.find((o) => o.id === id)?.name || id.slice(0, 8);

  const act = async (fn, msg) => {
    try {
      await fn();
      toast.success(msg);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Action failed");
    }
  };

  return (
    <div className="border-t border-[#2a2a2a] p-4" data-testid="org-links-panel">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <LinkIcon className="h-4 w-4 text-[#00f0ff]" />
          <h2 className="text-base font-semibold">Inter-Org Resource Sharing</h2>
        </div>
        <button
          data-testid="new-org-link-btn"
          onClick={() => setShowNew(true)}
          className="flex items-center gap-2 border border-[#00f0ff] bg-[#00f0ff]/10 px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#00f0ff] hover:bg-[#00f0ff]/20"
        >
          <Plus className="h-3 w-3" /> Propose Link
        </button>
      </div>

      {links.length === 0 && (
        <div className="border border-dashed border-[#2a2a2a] p-6 text-center mono text-xs text-neutral-500">
          No cross-organization links yet.
          <br />
          Link two orgs to share radios, positions, messages, voice, overlays, geofences, or emergency handling.
        </div>
      )}

      <div className="grid gap-2">
        {links.map((ln) => {
          const canApprove = ln.status === "pending" && (isSuperAdmin(user) || user.org_id === ln.to_org_id);
          const canRevoke = ln.status === "active" && (isSuperAdmin(user) || [ln.from_org_id, ln.to_org_id].includes(user.org_id));
          return (
            <div
              key={ln.id}
              data-testid={`org-link-${ln.id}`}
              className="border border-[#2a2a2a] bg-[#0a0a0a] p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 mono text-sm">
                  <span className="text-[#39ff14]">{orgName(ln.from_org_id)}</span>
                  <ArrowRight className="h-3 w-3 text-neutral-500" />
                  <span className="text-[#00f0ff]">{orgName(ln.to_org_id)}</span>
                  <span
                    className={`ml-2 mono border px-2 py-0.5 text-[10px] uppercase tracking-widest ${
                      ln.status === "active"
                        ? "border-[#39ff14]/40 text-[#39ff14]"
                        : ln.status === "pending"
                        ? "border-[#ffb800]/40 text-[#ffb800]"
                        : "border-[#ff3b30]/40 text-[#ff3b30]"
                    }`}
                  >
                    {ln.status}
                  </span>
                  <span className="border border-[#2a2a2a] px-2 py-0.5 mono text-[10px] uppercase tracking-widest text-neutral-400">
                    {ln.permissions}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  {canApprove && (
                    <button
                      data-testid={`approve-link-${ln.id}`}
                      title="Approve link"
                      onClick={() => act(() => approveOrgLink(ln.id), "Link approved")}
                      className="border border-[#2a2a2a] p-1.5 text-neutral-400 hover:text-[#39ff14] hover:border-[#39ff14]"
                    >
                      <Check className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {canRevoke && (
                    <button
                      data-testid={`revoke-link-${ln.id}`}
                      title="Revoke link"
                      onClick={() => act(() => revokeOrgLink(ln.id), "Link revoked")}
                      className="border border-[#2a2a2a] p-1.5 text-neutral-400 hover:text-[#ffb800] hover:border-[#ffb800]"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {isSuperAdmin(user) && (
                    <button
                      data-testid={`delete-link-${ln.id}`}
                      title="Delete link (super admin)"
                      onClick={() => {
                        if (window.confirm("Delete this link permanently?"))
                          act(() => deleteOrgLink(ln.id), "Link deleted");
                      }}
                      className="border border-[#2a2a2a] p-1.5 text-neutral-400 hover:text-[#ff3b30] hover:border-[#ff3b30]"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-1 mono text-[10px]">
                {SHARE_KEYS.filter((k) => ln.share?.[k]).map((k) => (
                  <span
                    key={k}
                    className="border border-[#2a2a2a] px-1.5 py-0.5 uppercase tracking-widest text-neutral-400"
                  >
                    {k}
                  </span>
                ))}
              </div>
              {ln.note && (
                <div className="mt-2 text-xs text-neutral-500 italic">&ldquo;{ln.note}&rdquo;</div>
              )}
            </div>
          );
        })}
      </div>

      {showNew && (
        <NewOrgLinkModal
          orgs={orgs}
          user={user}
          onClose={() => setShowNew(false)}
          onCreated={() => {
            setShowNew(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function NewOrgLinkModal({ orgs, user, onClose, onCreated }) {
  // The "from" org must be one this user administers.
  const canFromOrgs = isSuperAdmin(user) ? orgs : orgs.filter((o) => o.id === user.org_id);
  const [fromOrgId, setFromOrgId] = useState(canFromOrgs[0]?.id || "");
  const [toOrgId, setToOrgId] = useState("");
  const [permissions, setPermissions] = useState("view");
  const [share, setShare] = useState(
    SHARE_KEYS.reduce((acc, k) => ({ ...acc, [k]: true }), {})
  );
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (fromOrgId === toOrgId) {
      toast.error("Source and target orgs must differ");
      return;
    }
    setBusy(true);
    try {
      await createOrgLink({
        from_org_id: fromOrgId,
        to_org_id: toOrgId,
        permissions,
        share,
        note,
      });
      toast.success("Link proposed – awaiting recipient approval");
      onCreated();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to propose");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/70 p-4">
      <form
        onSubmit={submit}
        data-testid="new-org-link-modal"
        className="w-[480px] max-h-full overflow-y-auto border border-[#2a2a2a] bg-[#0a0a0a] p-4"
      >
        <div className="mono text-[10px] uppercase tracking-[0.3em] text-neutral-500">
          Propose Cross-Org Link
        </div>
        <h2 className="mb-3 text-lg font-semibold flex items-center gap-2">
          <Shield className="h-4 w-4 text-[#00f0ff]" /> Share Resources
        </h2>
        <p className="mb-4 text-xs text-neutral-500">
          The recipient org&apos;s admin must approve the link before it becomes active. Links are one-directional — resources flow from source ➜ target.
        </p>

        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          From (your org)
        </label>
        <select
          data-testid="link-from-org"
          value={fromOrgId}
          onChange={(e) => setFromOrgId(e.target.value)}
          className="mb-3 w-full border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
        >
          {canFromOrgs.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>

        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          To (recipient org)
        </label>
        <select
          data-testid="link-to-org"
          required
          value={toOrgId}
          onChange={(e) => setToOrgId(e.target.value)}
          className="mb-3 w-full border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
        >
          <option value="">— select organization —</option>
          {orgs
            .filter((o) => o.id !== fromOrgId)
            .map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
        </select>

        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Permissions
        </label>
        <div className="mb-3 flex gap-2">
          {["view", "view+dispatch"].map((p) => (
            <label
              key={p}
              className="flex flex-1 cursor-pointer items-center gap-2 border border-[#2a2a2a] px-2 py-1.5 mono text-xs hover:border-[#00f0ff]"
              style={{
                borderColor: permissions === p ? "#00f0ff" : undefined,
                color: permissions === p ? "#00f0ff" : undefined,
              }}
            >
              <input
                type="radio"
                name="perms"
                data-testid={`perms-${p}`}
                checked={permissions === p}
                onChange={() => setPermissions(p)}
              />
              {p}
            </label>
          ))}
        </div>

        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Shared resources
        </label>
        <div className="mb-3 grid grid-cols-2 gap-1">
          {SHARE_KEYS.map((k) => (
            <label key={k} className="flex items-center gap-2 mono text-xs">
              <input
                data-testid={`share-${k}`}
                type="checkbox"
                checked={!!share[k]}
                onChange={(e) => setShare({ ...share, [k]: e.target.checked })}
              />
              <span className="uppercase tracking-widest text-neutral-400">{k}</span>
            </label>
          ))}
        </div>

        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Note (optional)
        </label>
        <input
          data-testid="link-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. Event 2026 - Zone Alpha"
          className="mb-3 w-full border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
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
            data-testid="link-submit"
            type="submit"
            disabled={busy || !toOrgId}
            className="border border-[#00f0ff] bg-[#00f0ff]/10 px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#00f0ff] hover:bg-[#00f0ff]/20 disabled:opacity-50"
          >
            {busy ? "Proposing…" : "Propose Link"}
          </button>
        </div>
      </form>
    </div>
  );
}
