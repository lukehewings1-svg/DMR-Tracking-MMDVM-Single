import { useEffect, useState } from "react";
import {
  listSituationalTokens,
  createSituationalToken,
  deleteSituationalToken,
} from "@/lib/api";
import { toast } from "sonner";
import { Copy, Eye, Plus, Trash2, Radio, X } from "lucide-react";
import { formatDistanceToNowStrict } from "date-fns";

export function SituationalTokensPanel({ groups }) {
  const [tokens, setTokens] = useState([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [groupId, setGroupId] = useState("");
  const [expiresInDays, setExpiresInDays] = useState("");

  const load = async () => {
    try {
      setTokens(await listSituationalTokens());
    } catch {
      /* noop */
    }
  };

  useEffect(() => {
    load();
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const expires_at = expiresInDays
        ? new Date(Date.now() + Number(expiresInDays) * 86400_000).toISOString()
        : null;
      await createSituationalToken({
        name: name.trim(),
        group_id: groupId || null,
        expires_at,
      });
      toast.success("Link created");
      setName("");
      setGroupId("");
      setExpiresInDays("");
      setCreating(false);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to create");
    }
  };

  const remove = async (t) => {
    if (!window.confirm(`Revoke situational link "${t.name}"?`)) return;
    try {
      await deleteSituationalToken(t.id);
      toast.success("Revoked");
      load();
    } catch {
      toast.error("Failed to revoke");
    }
  };

  const urlFor = (t) => `${window.location.origin}/situational/${t.token}`;

  const copy = async (t) => {
    try {
      await navigator.clipboard.writeText(urlFor(t));
      toast.success("Link copied");
    } catch {
      toast.error("Clipboard blocked — long-press and copy manually");
    }
  };

  return (
    <section
      data-testid="situational-tokens-panel"
      className="border-b border-[#2a2a2a] px-4 py-3"
    >
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Eye className="h-3.5 w-3.5 text-[#00f0ff]" />
          <div className="mono text-[10px] uppercase tracking-[0.3em] text-neutral-400">
            Situational views (read-only links)
          </div>
        </div>
        <button
          data-testid="new-situational-token"
          onClick={() => setCreating(true)}
          className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 mono text-[10px] uppercase tracking-widest text-neutral-300 hover:border-[#00f0ff] hover:text-[#00f0ff]"
        >
          <Plus className="h-3 w-3" /> New
        </button>
      </div>

      {creating && (
        <form
          onSubmit={submit}
          data-testid="situational-token-form"
          className="mb-3 grid grid-cols-1 gap-2 border border-[#2a2a2a] bg-[#0a0a0a] p-3 md:grid-cols-4"
        >
          <input
            data-testid="situational-token-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Link name (e.g. Command Post)"
            className="border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] outline-none focus:border-[#00f0ff]"
          />
          <select
            data-testid="situational-token-group"
            value={groupId}
            onChange={(e) => setGroupId(e.target.value)}
            className="border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] outline-none focus:border-[#00f0ff]"
          >
            <option value="">All radios (no group scope)</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {`${g.name} (TG ${g.talkgroup_id})`}
              </option>
            ))}
          </select>
          <input
            data-testid="situational-token-expires"
            type="number"
            min="0"
            value={expiresInDays}
            onChange={(e) => setExpiresInDays(e.target.value)}
            placeholder="Expires in days (blank = never)"
            className="border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] outline-none focus:border-[#00f0ff]"
          />
          <div className="flex items-center justify-end gap-1">
            <button
              type="button"
              onClick={() => setCreating(false)}
              className="border border-[#2a2a2a] px-2 py-1 mono text-[10px] uppercase text-neutral-400 hover:border-neutral-500 hover:text-neutral-200"
            >
              <X className="h-3 w-3" />
            </button>
            <button
              data-testid="situational-token-create"
              type="submit"
              className="border border-[#39ff14] px-3 py-1 mono text-[10px] uppercase text-[#39ff14] hover:bg-[#39ff14] hover:text-black"
            >
              Create
            </button>
          </div>
        </form>
      )}

      {tokens.length === 0 && !creating && (
        <div className="mono text-[11px] text-neutral-500">
          No links yet. Create one to give command staff a view-only URL.
        </div>
      )}

      {tokens.length > 0 && (
        <ul className="space-y-1.5">
          {tokens.map((t) => {
            const group = groups.find((g) => g.id === t.group_id);
            const isExpired =
              t.expires_at && new Date(t.expires_at) < new Date();
            return (
              <li
                key={t.id}
                data-testid={`situational-token-${t.id}`}
                className={`grid grid-cols-[1fr_auto] items-center gap-2 border border-[#2a2a2a] bg-[#0a0a0a] p-2 ${
                  isExpired ? "opacity-50" : ""
                }`}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mono text-[12px]">
                    <span className="truncate text-neutral-100">{t.name}</span>
                    {group && (
                      <span
                        className="mono text-[9px] uppercase tracking-widest"
                        style={{ color: group.color || "#39ff14" }}
                      >
                        · {group.name}
                      </span>
                    )}
                    {!group && (
                      <span className="mono text-[9px] uppercase tracking-widest text-neutral-500">
                        · all radios
                      </span>
                    )}
                    {isExpired && (
                      <span className="mono text-[9px] uppercase tracking-widest text-[#ff3b30]">
                        · expired
                      </span>
                    )}
                  </div>
                  <div className="truncate mono text-[10px] text-neutral-500">
                    {urlFor(t)}
                  </div>
                  <div className="mono text-[9px] text-neutral-600">
                    created {formatDistanceToNowStrict(new Date(t.created_at))} ago
                    {t.expires_at && (
                      <> · expires {formatDistanceToNowStrict(new Date(t.expires_at))} {isExpired ? "ago" : "from now"}</>
                    )}
                    {t.created_by && <> · by {t.created_by}</>}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    data-testid={`situational-token-copy-${t.id}`}
                    onClick={() => copy(t)}
                    title="Copy link"
                    className="border border-[#2a2a2a] p-1 text-neutral-400 hover:border-[#00f0ff] hover:text-[#00f0ff]"
                  >
                    <Copy className="h-3 w-3" />
                  </button>
                  <a
                    data-testid={`situational-token-open-${t.id}`}
                    href={urlFor(t)}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="Open"
                    className="border border-[#2a2a2a] p-1 text-neutral-400 hover:border-[#39ff14] hover:text-[#39ff14]"
                  >
                    <Radio className="h-3 w-3" />
                  </a>
                  <button
                    data-testid={`situational-token-delete-${t.id}`}
                    onClick={() => remove(t)}
                    title="Revoke"
                    className="border border-[#2a2a2a] p-1 text-neutral-400 hover:border-[#ff3b30] hover:text-[#ff3b30]"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
