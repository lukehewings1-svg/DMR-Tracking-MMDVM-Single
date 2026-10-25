import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  createOverlay,
  deleteOverlay,
  deleteOverlayImage,
  listOverlays,
  updateOverlay,
  updateOverlayImage,
  uploadOverlayImage,
} from "@/lib/api";
import {
  ChevronDown,
  ChevronRight,
  ImageIcon,
  Layers,
  Plus,
  Trash2,
  Upload,
  Eye,
  EyeOff,
} from "lucide-react";

/**
 * Sidebar panel for admins.
 *
 * Manage overlay sets → activate/deactivate → upload event site maps → remove.
 * The parent (Dashboard) owns the "active editing target" (which set the
 * drawing toolbar writes into) and passes it down via `editingOverlayId` /
 * `onEditOverlay`.
 */
export function OverlayManagerPanel({
  editingOverlayId,
  onEditOverlay,
  currentMap,
  onOverlaysChanged,
}) {
  const [overlays, setOverlays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creatingName, setCreatingName] = useState("");
  const [expanded, setExpanded] = useState({});
  const fileInputRefs = useRef({});

  const refresh = async () => {
    try {
      const data = await listOverlays();
      setOverlays(data);
      onOverlaysChanged?.(data);
    } catch (e) {
      toast.error("Failed to load overlays");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submitCreate = async (e) => {
    e.preventDefault();
    const name = creatingName.trim();
    if (!name) return;
    try {
      const ov = await createOverlay(name);
      setCreatingName("");
      toast.success(`Overlay "${name}" created`);
      refresh();
      onEditOverlay?.(ov.id);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to create");
    }
  };

  const toggleActive = async (ov) => {
    try {
      await updateOverlay(ov.id, { active: !ov.active });
      refresh();
    } catch {
      toast.error("Failed to toggle");
    }
  };

  const rename = async (ov) => {
    const name = window.prompt("Rename overlay:", ov.name);
    if (!name || name === ov.name) return;
    try {
      await updateOverlay(ov.id, { name });
      refresh();
    } catch {
      toast.error("Failed to rename");
    }
  };

  const remove = async (ov) => {
    if (
      !window.confirm(
        `Delete overlay "${ov.name}" and all its shapes + images? This cannot be undone.`
      )
    )
      return;
    try {
      await deleteOverlay(ov.id);
      toast.success("Deleted");
      if (editingOverlayId === ov.id) onEditOverlay?.(null);
      refresh();
    } catch {
      toast.error("Failed to delete");
    }
  };

  const onUpload = async (ov, file) => {
    if (!file) return;
    if (!currentMap) {
      toast.error("Map not ready yet — pan the map first.");
      return;
    }
    const bounds = currentMap.getBounds();
    // Fit the image into the middle 60% of the current viewport by default so
    // the admin can immediately grab the corners to reposition.
    const swLat = bounds.getSouth() + (bounds.getNorth() - bounds.getSouth()) * 0.2;
    const swLng = bounds.getWest() + (bounds.getEast() - bounds.getWest()) * 0.2;
    const neLat = bounds.getSouth() + (bounds.getNorth() - bounds.getSouth()) * 0.8;
    const neLng = bounds.getWest() + (bounds.getEast() - bounds.getWest()) * 0.8;

    const form = new FormData();
    form.append("file", file);
    form.append("name", file.name);
    form.append("sw_lat", swLat);
    form.append("sw_lng", swLng);
    form.append("ne_lat", neLat);
    form.append("ne_lng", neLng);
    form.append("opacity", "0.65");
    try {
      await uploadOverlayImage(ov.id, form);
      toast.success("Image uploaded. Drag the corners to place it.");
      refresh();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    }
  };

  const removeImage = async (ov, image) => {
    if (!window.confirm(`Remove image "${image.name}"?`)) return;
    try {
      await deleteOverlayImage(ov.id, image.id);
      refresh();
    } catch {
      toast.error("Failed to remove image");
    }
  };

  const setImageOpacity = async (ov, image, opacity) => {
    try {
      await updateOverlayImage(ov.id, image.id, { opacity });
      refresh();
    } catch {
      /* noop */
    }
  };

  return (
    <section
      data-testid="overlay-manager"
      className="border-b border-[#2a2a2a] bg-[#050505]"
    >
      <div className="flex items-center justify-between px-3 py-2">
        <div className="flex items-center gap-2">
          <Layers className="h-3.5 w-3.5 text-[#00f0ff]" />
          <div className="mono text-[10px] uppercase tracking-[0.3em] text-neutral-400">
            Event overlays
          </div>
        </div>
      </div>

      <form
        onSubmit={submitCreate}
        data-testid="overlay-create-form"
        className="flex items-center gap-1 px-3 pb-2"
      >
        <input
          data-testid="overlay-create-name"
          value={creatingName}
          onChange={(e) => setCreatingName(e.target.value)}
          placeholder="New overlay set (e.g. Halloween Run 2026)"
          className="min-w-0 flex-1 border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] outline-none focus:border-[#00f0ff]"
        />
        <button
          data-testid="overlay-create-btn"
          type="submit"
          className="flex items-center gap-1 border border-[#39ff14] px-2 py-1 mono text-[10px] uppercase text-[#39ff14] hover:bg-[#39ff14] hover:text-black"
        >
          <Plus className="h-3 w-3" /> Add
        </button>
      </form>

      <div className="max-h-[300px] overflow-y-auto">
        {loading && (
          <div className="px-3 pb-3 mono text-[11px] text-neutral-500">loading…</div>
        )}
        {!loading && overlays.length === 0 && (
          <div className="px-3 pb-3 mono text-[11px] text-neutral-500">
            No overlay sets yet. Create one, draw on the map, and toggle it on
            when the event goes live.
          </div>
        )}
        <ul className="divide-y divide-[#1a1a1a]">
          {overlays.map((ov) => {
            const isEditing = editingOverlayId === ov.id;
            const isOpen = !!expanded[ov.id];
            return (
              <li
                key={ov.id}
                data-testid={`overlay-item-${ov.id}`}
                className={`px-3 py-2 ${
                  isEditing ? "bg-[#0a141a] border-l-2 border-[#00f0ff]" : ""
                }`}
              >
                <div className="flex items-center gap-2">
                  <button
                    onClick={() =>
                      setExpanded((e) => ({ ...e, [ov.id]: !e[ov.id] }))
                    }
                    className="text-neutral-500 hover:text-neutral-200"
                  >
                    {isOpen ? (
                      <ChevronDown className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5" />
                    )}
                  </button>
                  <button
                    data-testid={`overlay-toggle-active-${ov.id}`}
                    onClick={() => toggleActive(ov)}
                    title={ov.active ? "Turn off" : "Turn on"}
                    className={`border px-1.5 py-0.5 mono text-[9px] uppercase tracking-widest ${
                      ov.active
                        ? "border-[#39ff14] text-[#39ff14]"
                        : "border-[#2a2a2a] text-neutral-500"
                    }`}
                  >
                    {ov.active ? (
                      <span className="flex items-center gap-1">
                        <Eye className="h-3 w-3" /> On
                      </span>
                    ) : (
                      <span className="flex items-center gap-1">
                        <EyeOff className="h-3 w-3" /> Off
                      </span>
                    )}
                  </button>
                  <button
                    data-testid={`overlay-edit-${ov.id}`}
                    onClick={() => onEditOverlay?.(isEditing ? null : ov.id)}
                    className={`flex-1 truncate text-left mono text-[12px] ${
                      isEditing ? "text-[#00f0ff]" : "text-neutral-100 hover:text-[#00f0ff]"
                    }`}
                    title={
                      isEditing ? "Stop editing this set" : "Edit shapes on the map"
                    }
                  >
                    {ov.name}
                    {isEditing && (
                      <span className="ml-2 mono text-[9px] uppercase tracking-widest text-[#00f0ff]">
                        · editing
                      </span>
                    )}
                  </button>
                  <span className="mono text-[9px] text-neutral-500">
                    {ov.shapes?.length || 0}s · {ov.images?.length || 0}i
                  </span>
                  <button
                    data-testid={`overlay-rename-${ov.id}`}
                    onClick={() => rename(ov)}
                    title="Rename"
                    className="border border-[#2a2a2a] p-1 text-neutral-400 hover:border-[#00f0ff] hover:text-[#00f0ff]"
                  >
                    <span className="mono text-[9px]">Aa</span>
                  </button>
                  <button
                    data-testid={`overlay-delete-${ov.id}`}
                    onClick={() => remove(ov)}
                    title="Delete"
                    className="border border-[#2a2a2a] p-1 text-neutral-400 hover:border-[#ff3b30] hover:text-[#ff3b30]"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>

                {isOpen && (
                  <div className="mt-2 space-y-2 pl-6">
                    <div className="flex items-center gap-2">
                      <input
                        ref={(el) => (fileInputRefs.current[ov.id] = el)}
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/gif"
                        hidden
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          onUpload(ov, f);
                          e.target.value = "";
                        }}
                      />
                      <button
                        data-testid={`overlay-upload-${ov.id}`}
                        onClick={() => fileInputRefs.current[ov.id]?.click()}
                        className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 mono text-[10px] uppercase text-neutral-300 hover:border-[#00f0ff] hover:text-[#00f0ff]"
                      >
                        <Upload className="h-3 w-3" /> Upload map image
                      </button>
                      <span className="mono text-[10px] text-neutral-500">
                        PNG/JPG · &lt;20 MB
                      </span>
                    </div>

                    {(ov.images || []).length > 0 && (
                      <ul className="space-y-1.5">
                        {ov.images.map((img) => (
                          <li
                            key={img.id}
                            data-testid={`overlay-image-${img.id}`}
                            className="flex items-center gap-2 border border-[#1a1a1a] bg-[#0a0a0a] p-1.5"
                          >
                            <ImageIcon className="h-3.5 w-3.5 shrink-0 text-[#00f0ff]" />
                            <div className="min-w-0 flex-1">
                              <div className="truncate mono text-[11px] text-neutral-100">
                                {img.name}
                              </div>
                              <div className="mt-0.5 flex items-center gap-2">
                                <span className="mono text-[9px] text-neutral-500">
                                  opacity
                                </span>
                                <input
                                  data-testid={`overlay-image-opacity-${img.id}`}
                                  type="range"
                                  min="0.1"
                                  max="1"
                                  step="0.05"
                                  defaultValue={img.opacity ?? 0.6}
                                  onChange={(e) =>
                                    setImageOpacity(ov, img, Number(e.target.value))
                                  }
                                  className="h-1 flex-1 accent-[#00f0ff]"
                                />
                              </div>
                            </div>
                            <button
                              data-testid={`overlay-image-delete-${img.id}`}
                              onClick={() => removeImage(ov, img)}
                              className="border border-[#2a2a2a] p-1 text-neutral-400 hover:border-[#ff3b30] hover:text-[#ff3b30]"
                              title="Remove image"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
