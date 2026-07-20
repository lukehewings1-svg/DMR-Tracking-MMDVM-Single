import { useEffect, useState } from "react";
import {
  listEvents,
  createEvent,
  addEventParticipant,
  removeEventParticipant,
  startEvent,
  endEvent,
  deleteEvent,
  attachEventOverlay,
  detachEventOverlay,
  isAdmin,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import {
  Calendar,
  Play,
  Square,
  Plus,
  Trash2,
  Users as UsersIcon,
  MapPin,
  Zap,
  X,
} from "lucide-react";

const SHARE_KEYS = ["radios", "positions", "messages", "voice", "overlays", "geofences", "emergencies"];

const STATUS_COLORS = {
  planned: { border: "border-[#00f0ff]/40", text: "text-[#00f0ff]" },
  active: { border: "border-[#39ff14]/40", text: "text-[#39ff14]" },
  ended: { border: "border-neutral-500/40", text: "text-neutral-400" },
};

export function EventsPanel({ orgs, overlays = [] }) {
  const { user } = useAuth();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [managing, setManaging] = useState(null);

  const load = async () => {
    try {
      setEvents(await listEvents());
    } catch (e) {
      toast.error("Failed to load events");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin(user)) load();
  }, [user]);

  if (!isAdmin(user)) return null;

  const orgName = (id) => orgs.find((o) => o.id === id)?.name || id?.slice(0, 8);

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
    <div className="border-t border-[#2a2a2a] p-4" data-testid="events-panel">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-[#ffb800]" />
          <h2 className="text-base font-semibold">Event Sessions</h2>
          <span className="mono text-[10px] uppercase tracking-widest text-neutral-500">
            multi-agency one-click coordination
          </span>
        </div>
        <button
          data-testid="new-event-btn"
          onClick={() => setShowNew(true)}
          className="flex items-center gap-2 border border-[#ffb800] bg-[#ffb800]/10 px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#ffb800] hover:bg-[#ffb800]/20"
        >
          <Plus className="h-3 w-3" /> New Event
        </button>
      </div>

      {loading && (
        <div className="p-4 mono text-xs text-neutral-500">loading events…</div>
      )}

      {!loading && events.length === 0 && (
        <div className="border border-dashed border-[#2a2a2a] p-6 text-center mono text-xs text-neutral-500">
          No events yet. Create one to bundle orgs + overlays + geofences and one-click
          switch every linked org into a shared operational picture.
        </div>
      )}

      <div className="grid gap-2">
        {events.map((ev) => {
          const sc = STATUS_COLORS[ev.status] || STATUS_COLORS.planned;
          const isHost = user.role === "super_admin" || user.org_id === ev.host_org_id;
          return (
            <div
              key={ev.id}
              data-testid={`event-card-${ev.id}`}
              className="border border-[#2a2a2a] bg-[#0a0a0a] p-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="text-sm font-semibold text-neutral-100">
                      {ev.name}
                    </div>
                    <span
                      className={`mono border px-2 py-0.5 text-[10px] uppercase tracking-widest ${sc.border} ${sc.text}`}
                    >
                      {ev.status}
                    </span>
                    <span className="border border-[#2a2a2a] px-2 py-0.5 mono text-[10px] uppercase tracking-widest text-neutral-400">
                      {ev.permissions}
                    </span>
                    {ev.status === "active" && (
                      <span className="flex items-center gap-1 mono text-[10px] text-[#39ff14]">
                        <Zap className="h-3 w-3 animate-pulse" /> live
                      </span>
                    )}
                  </div>
                  {ev.description && (
                    <div className="mt-1 text-xs text-neutral-400">{ev.description}</div>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-3 mono text-[11px] text-neutral-400">
                    <span className="flex items-center gap-1">
                      <UsersIcon className="h-3 w-3" />
                      {(ev.participant_org_ids || []).length} orgs · host {orgName(ev.host_org_id)}
                    </span>
                    {(ev.overlay_ids || []).length > 0 && (
                      <span className="flex items-center gap-1">
                        <MapPin className="h-3 w-3" />
                        {(ev.overlay_ids || []).length} overlay{ev.overlay_ids.length === 1 ? "" : "s"}
                      </span>
                    )}
                    {ev.end_at && (
                      <span className="text-neutral-500">
                        auto-ends {new Date(ev.end_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>
                {isHost && (
                  <div className="flex items-center gap-1">
                    {ev.status === "planned" && (
                      <button
                        data-testid={`start-event-${ev.id}`}
                        title="Start event"
                        onClick={() => act(() => startEvent(ev.id), "Event started")}
                        className="flex items-center gap-1 border border-[#39ff14] bg-[#39ff14]/10 px-2 py-1 mono text-[10px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14]/20"
                      >
                        <Play className="h-3 w-3" /> Start
                      </button>
                    )}
                    {ev.status === "active" && (
                      <button
                        data-testid={`end-event-${ev.id}`}
                        title="End event"
                        onClick={() => {
                          if (window.confirm(`End "${ev.name}"? All event links will be revoked.`))
                            act(() => endEvent(ev.id), "Event ended");
                        }}
                        className="flex items-center gap-1 border border-[#ff3b30] bg-[#ff3b30]/10 px-2 py-1 mono text-[10px] uppercase tracking-widest text-[#ff3b30] hover:bg-[#ff3b30]/20"
                      >
                        <Square className="h-3 w-3" /> End
                      </button>
                    )}
                    <button
                      data-testid={`manage-event-${ev.id}`}
                      onClick={() => setManaging(ev)}
                      className="border border-[#2a2a2a] p-1.5 text-neutral-400 hover:text-[#00f0ff] hover:border-[#00f0ff]"
                      title="Manage participants + overlays"
                    >
                      <UsersIcon className="h-3.5 w-3.5" />
                    </button>
                    {ev.status !== "active" && (
                      <button
                        data-testid={`delete-event-${ev.id}`}
                        onClick={() => {
                          if (window.confirm(`Delete event "${ev.name}"?`))
                            act(() => deleteEvent(ev.id), "Event deleted");
                        }}
                        className="border border-[#2a2a2a] p-1.5 text-neutral-400 hover:text-[#ff3b30] hover:border-[#ff3b30]"
                        title="Delete event"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                )}
              </div>

              {(ev.participant_org_ids || []).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {ev.participant_org_ids.map((oid) => (
                    <span
                      key={oid}
                      className="border border-[#2a2a2a] px-1.5 py-0.5 mono text-[10px] uppercase tracking-widest text-neutral-400"
                    >
                      {orgName(oid)}
                      {oid === ev.host_org_id && (
                        <span className="ml-1 text-[#ffb800]">HOST</span>
                      )}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {showNew && (
        <NewEventModal
          orgs={orgs}
          user={user}
          onClose={() => setShowNew(false)}
          onCreated={() => {
            setShowNew(false);
            load();
          }}
        />
      )}

      {managing && (
        <ManageEventModal
          event={managing}
          orgs={orgs}
          overlays={overlays}
          onClose={() => setManaging(null)}
          onChange={load}
        />
      )}
    </div>
  );
}

function NewEventModal({ orgs, user, onClose, onCreated }) {
  const hostableOrgs =
    user.role === "super_admin" ? orgs : orgs.filter((o) => o.id === user.org_id);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [hostOrgId, setHostOrgId] = useState(hostableOrgs[0]?.id || "");
  const [permissions, setPermissions] = useState("view+dispatch");
  const [endAt, setEndAt] = useState("");
  const [share, setShare] = useState(
    SHARE_KEYS.reduce((acc, k) => ({ ...acc, [k]: true }), {})
  );
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await createEvent({
        name,
        description,
        host_org_id: hostOrgId,
        end_at: endAt ? new Date(endAt).toISOString() : null,
        permissions,
        share,
      });
      toast.success("Event created");
      onCreated();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to create");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/70 p-4">
      <form
        onSubmit={submit}
        data-testid="new-event-modal"
        className="w-[520px] max-h-full overflow-y-auto border border-[#2a2a2a] bg-[#0a0a0a] p-4"
      >
        <div className="mono text-[10px] uppercase tracking-[0.3em] text-neutral-500">
          New Event Session
        </div>
        <h2 className="mb-3 text-lg font-semibold flex items-center gap-2">
          <Calendar className="h-4 w-4 text-[#ffb800]" /> Multi-Agency Bundle
        </h2>
        <p className="mb-4 text-xs text-neutral-500">
          On <span className="text-[#39ff14]">start</span>, every participant org will be linked to every other participant with the settings below.
          On <span className="text-[#ff3b30]">end</span> (manual or auto at end-time), those links revoke.
        </p>

        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Name
        </label>
        <input
          data-testid="event-name"
          required
          autoFocus
          placeholder="e.g. Halloween Run 2026 – Multi-Agency"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mb-3 w-full border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-sm text-neutral-100 outline-none focus:border-[#ffb800]"
        />

        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Description (optional)
        </label>
        <textarea
          data-testid="event-description"
          rows={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="mb-3 w-full border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-sm text-neutral-100 outline-none focus:border-[#ffb800]"
        />

        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Host organization
        </label>
        <select
          data-testid="event-host-org"
          value={hostOrgId}
          onChange={(e) => setHostOrgId(e.target.value)}
          className="mb-3 w-full border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-sm text-neutral-100 outline-none focus:border-[#ffb800]"
        >
          {hostableOrgs.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>

        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Auto-end at (optional; UTC)
        </label>
        <input
          data-testid="event-end-at"
          type="datetime-local"
          value={endAt}
          onChange={(e) => setEndAt(e.target.value)}
          className="mb-3 w-full border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-sm text-neutral-100 outline-none focus:border-[#ffb800]"
        />

        <label className="mono text-[10px] uppercase tracking-widest text-neutral-500">
          Cross-org permissions
        </label>
        <div className="mb-3 flex gap-2">
          {["view", "view+dispatch"].map((p) => (
            <label
              key={p}
              className="flex flex-1 cursor-pointer items-center gap-2 border border-[#2a2a2a] px-2 py-1.5 mono text-xs hover:border-[#ffb800]"
              style={{
                borderColor: permissions === p ? "#ffb800" : undefined,
                color: permissions === p ? "#ffb800" : undefined,
              }}
            >
              <input
                type="radio"
                name="event-perms"
                data-testid={`event-perms-${p}`}
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
        <div className="mb-4 grid grid-cols-2 gap-1">
          {SHARE_KEYS.map((k) => (
            <label key={k} className="flex items-center gap-2 mono text-xs">
              <input
                data-testid={`event-share-${k}`}
                type="checkbox"
                checked={!!share[k]}
                onChange={(e) => setShare({ ...share, [k]: e.target.checked })}
              />
              <span className="uppercase tracking-widest text-neutral-400">{k}</span>
            </label>
          ))}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="border border-[#2a2a2a] px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-neutral-400 hover:text-neutral-200"
          >
            Cancel
          </button>
          <button
            data-testid="create-event-submit"
            type="submit"
            disabled={busy}
            className="border border-[#ffb800] bg-[#ffb800]/10 px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#ffb800] hover:bg-[#ffb800]/20 disabled:opacity-50"
          >
            {busy ? "Creating…" : "Create Event"}
          </button>
        </div>
      </form>
    </div>
  );
}

function ManageEventModal({ event, orgs, overlays, onClose, onChange }) {
  const [participantOrgId, setParticipantOrgId] = useState("");
  const [overlayId, setOverlayId] = useState("");
  const otherOrgs = orgs.filter((o) => !event.participant_org_ids?.includes(o.id));
  const otherOverlays = overlays.filter((o) => !event.overlay_ids?.includes(o.id));

  const act = async (fn, msg) => {
    try {
      await fn();
      toast.success(msg);
      onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  return (
    <div className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/70 p-4">
      <div
        data-testid="manage-event-modal"
        className="w-[520px] max-h-full overflow-y-auto border border-[#2a2a2a] bg-[#0a0a0a] p-4"
      >
        <div className="mb-3 flex items-center justify-between">
          <div>
            <div className="mono text-[10px] uppercase tracking-[0.3em] text-neutral-500">
              Manage Event
            </div>
            <div className="text-lg font-semibold">{event.name}</div>
          </div>
          <button
            onClick={onClose}
            className="border border-[#2a2a2a] p-1.5 text-neutral-400 hover:text-neutral-100"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mb-4">
          <div className="mb-2 mono text-[10px] uppercase tracking-widest text-neutral-500">
            Participant organizations
          </div>
          <div className="mb-2 flex flex-wrap gap-1">
            {event.participant_org_ids.map((oid) => {
              const org = orgs.find((o) => o.id === oid);
              const isHost = oid === event.host_org_id;
              return (
                <span
                  key={oid}
                  className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 mono text-[11px] text-neutral-300"
                >
                  {org?.name || oid.slice(0, 8)}
                  {isHost && <span className="text-[#ffb800]">HOST</span>}
                  {!isHost && event.status !== "active" && (
                    <button
                      data-testid={`remove-participant-${oid}`}
                      onClick={() =>
                        act(
                          () => removeEventParticipant(event.id, oid),
                          "Participant removed"
                        )
                      }
                      className="text-neutral-500 hover:text-[#ff3b30]"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </span>
              );
            })}
          </div>
          {otherOrgs.length > 0 && (
            <div className="flex items-center gap-2">
              <select
                data-testid="add-participant-select"
                value={participantOrgId}
                onChange={(e) => setParticipantOrgId(e.target.value)}
                className="flex-1 border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-xs text-neutral-100 outline-none focus:border-[#00f0ff]"
              >
                <option value="">— add org —</option>
                {otherOrgs.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
              <button
                data-testid="add-participant-btn"
                disabled={!participantOrgId}
                onClick={() => {
                  act(
                    () => addEventParticipant(event.id, participantOrgId),
                    "Participant added"
                  );
                  setParticipantOrgId("");
                }}
                className="border border-[#00f0ff] bg-[#00f0ff]/10 px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#00f0ff] hover:bg-[#00f0ff]/20 disabled:opacity-50"
              >
                Add
              </button>
            </div>
          )}
        </div>

        <div>
          <div className="mb-2 mono text-[10px] uppercase tracking-widest text-neutral-500">
            Attached overlays
          </div>
          <div className="mb-2 flex flex-wrap gap-1">
            {(event.overlay_ids || []).map((oid) => {
              const ov = overlays.find((o) => o.id === oid);
              return (
                <span
                  key={oid}
                  className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 mono text-[11px] text-neutral-300"
                >
                  <MapPin className="h-3 w-3 text-[#00f0ff]" />
                  {ov?.name || oid.slice(0, 8)}
                  <button
                    data-testid={`detach-overlay-${oid}`}
                    onClick={() =>
                      act(() => detachEventOverlay(event.id, oid), "Overlay detached")
                    }
                    className="text-neutral-500 hover:text-[#ff3b30]"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              );
            })}
            {(event.overlay_ids || []).length === 0 && (
              <span className="mono text-[11px] text-neutral-500">
                No overlays attached
              </span>
            )}
          </div>
          {otherOverlays.length > 0 && (
            <div className="flex items-center gap-2">
              <select
                data-testid="attach-overlay-select"
                value={overlayId}
                onChange={(e) => setOverlayId(e.target.value)}
                className="flex-1 border border-[#2a2a2a] bg-black px-2 py-1.5 mono text-xs text-neutral-100 outline-none focus:border-[#00f0ff]"
              >
                <option value="">— attach overlay —</option>
                {otherOverlays.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
              <button
                data-testid="attach-overlay-btn"
                disabled={!overlayId}
                onClick={() => {
                  act(
                    () => attachEventOverlay(event.id, overlayId),
                    "Overlay attached"
                  );
                  setOverlayId("");
                }}
                className="border border-[#00f0ff] bg-[#00f0ff]/10 px-3 py-1.5 mono text-[11px] uppercase tracking-widest text-[#00f0ff] hover:bg-[#00f0ff]/20 disabled:opacity-50"
              >
                Attach
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
