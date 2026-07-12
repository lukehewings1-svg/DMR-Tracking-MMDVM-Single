import { useEffect, useState } from "react";
import {
  listGeofences,
  createGeofence,
  deleteGeofence,
  listAlerts,
  clearAlerts,
} from "@/lib/api";
import { toast } from "sonner";
import { Trash2, Plus, Bell, BellRing } from "lucide-react";
import { formatDistanceToNowStrict } from "date-fns";
import { useAuth } from "@/context/AuthContext";

export function GeofencePanel({ onChange }) {
  const { user } = useAuth();
  const [fences, setFences] = useState([]);
  const [name, setName] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [radius, setRadius] = useState(1000);
  const [alertOn, setAlertOn] = useState("both");
  const [showForm, setShowForm] = useState(false);
  const isAdmin = user?.role === "admin";

  const reload = async () => {
    try {
      setFences(await listGeofences());
    } catch {
      /* noop */
    }
  };
  useEffect(() => {
    reload();
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await createGeofence({
        name,
        lat: parseFloat(lat),
        lon: parseFloat(lon),
        radius_m: parseFloat(radius),
        alert_on: alertOn,
      });
      toast.success("Geofence created");
      setName("");
      setLat("");
      setLon("");
      setRadius(1000);
      setShowForm(false);
      reload();
      onChange?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to create");
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete geofence?")) return;
    await deleteGeofence(id);
    toast.success("Geofence deleted");
    reload();
    onChange?.();
  };

  return (
    <div className="border-b border-[#2a2a2a] p-3" data-testid="geofence-panel">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">
          Geofences
        </div>
        {isAdmin && (
          <button
            data-testid="geofence-toggle-form"
            onClick={() => setShowForm((s) => !s)}
            className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-0.5 mono text-[10px] uppercase text-neutral-400 hover:border-[#00f0ff] hover:text-[#00f0ff]"
          >
            <Plus className="h-3 w-3" /> New
          </button>
        )}
      </div>

      {showForm && isAdmin && (
        <form
          onSubmit={submit}
          data-testid="geofence-form"
          className="mb-2 space-y-1.5 border border-[#2a2a2a] p-2"
        >
          <input
            data-testid="geofence-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name (e.g. Base)"
            className="w-full border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] text-neutral-100 outline-none focus:border-[#00f0ff]"
          />
          <div className="grid grid-cols-2 gap-1.5">
            <input
              data-testid="geofence-lat"
              required
              type="number"
              step="any"
              value={lat}
              onChange={(e) => setLat(e.target.value)}
              placeholder="Latitude"
              className="border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] text-neutral-100 outline-none focus:border-[#00f0ff]"
            />
            <input
              data-testid="geofence-lon"
              required
              type="number"
              step="any"
              value={lon}
              onChange={(e) => setLon(e.target.value)}
              placeholder="Longitude"
              className="border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] text-neutral-100 outline-none focus:border-[#00f0ff]"
            />
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            <input
              data-testid="geofence-radius"
              required
              type="number"
              min="10"
              value={radius}
              onChange={(e) => setRadius(e.target.value)}
              placeholder="Radius (m)"
              className="border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] text-neutral-100 outline-none focus:border-[#00f0ff]"
            />
            <select
              data-testid="geofence-alerton"
              value={alertOn}
              onChange={(e) => setAlertOn(e.target.value)}
              className="border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] text-neutral-100 outline-none focus:border-[#00f0ff]"
            >
              <option value="enter">Alert on Enter</option>
              <option value="exit">Alert on Exit</option>
              <option value="both">Alert on Both</option>
            </select>
          </div>
          <button
            data-testid="geofence-submit"
            type="submit"
            className="w-full border border-[#39ff14] bg-[#0a1a0a] px-2 py-1 mono text-[10px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14] hover:text-black"
          >
            Create Geofence
          </button>
        </form>
      )}

      {fences.length === 0 && (
        <div className="mono text-[10px] text-neutral-600">
          No geofences defined.
        </div>
      )}
      <div className="space-y-1">
        {fences.map((f) => (
          <div
            key={f.id}
            data-testid={`geofence-row-${f.id}`}
            className="flex items-center justify-between border border-[#2a2a2a] px-2 py-1 mono text-[11px]"
          >
            <div className="min-w-0">
              <div className="truncate text-neutral-100">{f.name}</div>
              <div className="text-[10px] text-neutral-500">
                {f.lat.toFixed(3)}, {f.lon.toFixed(3)} · {formatRadius(f.radius_m)} ·{" "}
                {f.alert_on}
              </div>
            </div>
            {isAdmin && (
              <button
                data-testid={`geofence-delete-${f.id}`}
                onClick={() => remove(f.id)}
                className="text-neutral-500 hover:text-[#ff3b30]"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function AlertsPanel({ alerts, onClear }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  return (
    <div className="border-b border-[#2a2a2a] p-3" data-testid="alerts-panel">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.3em] text-neutral-500">
          {alerts.length > 0 ? (
            <BellRing className="h-3 w-3 text-[#ffb800] animate-pulse" />
          ) : (
            <Bell className="h-3 w-3" />
          )}
          Alerts
        </div>
        {isAdmin && alerts.length > 0 && (
          <button
            data-testid="alerts-clear"
            onClick={onClear}
            className="mono text-[10px] uppercase text-neutral-500 hover:text-[#ff3b30]"
          >
            clear
          </button>
        )}
      </div>
      <div className="max-h-40 overflow-y-auto space-y-1">
        {alerts.length === 0 && (
          <div className="mono text-[10px] text-neutral-600">// no alerts</div>
        )}
        {alerts.map((a) => (
          <div
            key={a.id}
            data-testid={`alert-${a.id}`}
            className="border border-[#2a2a2a] px-2 py-1 mono text-[11px]"
          >
            <div className="flex items-center justify-between">
              <span
                className={
                  a.event === "enter" ? "text-[#39ff14]" : "text-[#ffb800]"
                }
              >
                {a.event.toUpperCase()}
              </span>
              <span className="text-[10px] text-neutral-500">
                {a.timestamp
                  ? formatDistanceToNowStrict(new Date(a.timestamp)) + " ago"
                  : "—"}
              </span>
            </div>
            <div className="text-neutral-200">
              {a.callsign || `ID ${a.dmr_id}`} → {a.fence_name}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatRadius(m) {
  if (m >= 1000) return `${(m / 1000).toFixed(1)} km`;
  return `${Math.round(m)} m`;
}
