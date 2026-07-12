import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  adminListUsers,
  adminApproveUser,
  adminRejectUser,
  adminSetRole,
  adminDeleteUser,
} from "@/lib/api";
import { toast } from "sonner";
import { ArrowLeft, Check, X, ShieldCheck, User as UserIcon, Trash2 } from "lucide-react";
import { formatDistanceToNowStrict } from "date-fns";
import { useAuth } from "@/context/AuthContext";

const STATUS_STYLE = {
  approved: "text-[#39ff14] border-[#39ff14]/40",
  pending: "text-[#ffb800] border-[#ffb800]/40",
  rejected: "text-[#ff3b30] border-[#ff3b30]/40",
};

export default function AdminUsers() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  const load = async () => {
    try {
      setUsers(await adminListUsers());
    } catch (e) {
      toast.error("Failed to load users");
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
      toast.success(msg);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Action failed");
    }
  };

  const filtered = users.filter(
    (u) => filter === "all" || u.status === filter
  );
  const pendingCount = users.filter((u) => u.status === "pending").length;

  return (
    <div className="h-screen bg-[#050505] text-neutral-100" data-testid="admin-users">
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
              Administration
            </div>
            <h1 className="text-lg font-semibold">User Access Control</h1>
          </div>
        </div>
        <div className="flex items-center gap-3 mono text-[11px] text-neutral-400">
          <span>Signed in as</span>
          <span className="text-neutral-100">{user?.email}</span>
        </div>
      </header>

      <div className="border-b border-[#2a2a2a] bg-[#0a0a0a] px-4 py-2 flex items-center gap-2 mono text-[11px]">
        {["all", "pending", "approved", "rejected"].map((f) => (
          <button
            key={f}
            data-testid={`filter-${f}`}
            onClick={() => setFilter(f)}
            className={`border px-3 py-1 uppercase tracking-widest transition-colors ${
              filter === f
                ? "border-[#39ff14] text-[#39ff14]"
                : "border-[#2a2a2a] text-neutral-400 hover:text-neutral-200"
            }`}
          >
            {f}
            {f === "pending" && pendingCount > 0 && (
              <span className="ml-2 rounded-full bg-[#ffb800] px-1.5 text-[9px] text-black">
                {pendingCount}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="overflow-y-auto" style={{ maxHeight: "calc(100vh - 108px)" }}>
        {loading && (
          <div className="p-10 text-center mono text-xs text-neutral-500">
            loading…
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="p-10 text-center mono text-xs text-neutral-500">
            no users match this filter
          </div>
        )}
        <table className="w-full">
          <thead className="mono text-[10px] uppercase tracking-widest text-neutral-500">
            <tr className="border-b border-[#2a2a2a]">
              <th className="px-4 py-2 text-left">Email</th>
              <th className="px-4 py-2 text-left">Callsign</th>
              <th className="px-4 py-2 text-left">Role</th>
              <th className="px-4 py-2 text-left">Status</th>
              <th className="px-4 py-2 text-left">Created</th>
              <th className="px-4 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((u) => (
              <tr
                key={u.id}
                data-testid={`user-row-${u.id}`}
                className="border-b border-[#1a1a1a] hover:bg-[#0a0a0a]"
              >
                <td className="px-4 py-3 mono text-sm">{u.email}</td>
                <td className="px-4 py-3 mono text-xs text-neutral-400">
                  {u.callsign || "—"}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`mono text-[10px] uppercase tracking-widest ${
                      u.role === "admin" ? "text-[#00f0ff]" : "text-neutral-400"
                    }`}
                  >
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`mono border px-2 py-0.5 text-[10px] uppercase tracking-widest ${
                      STATUS_STYLE[u.status] || "text-neutral-400 border-[#2a2a2a]"
                    }`}
                  >
                    {u.status}
                  </span>
                </td>
                <td className="px-4 py-3 mono text-[11px] text-neutral-500">
                  {u.created_at
                    ? formatDistanceToNowStrict(new Date(u.created_at)) + " ago"
                    : "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1">
                    {u.status !== "approved" && (
                      <IconBtn
                        testid={`approve-${u.id}`}
                        onClick={() =>
                          act(() => adminApproveUser(u.id), "Approved")
                        }
                        title="Approve"
                        color="#39ff14"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </IconBtn>
                    )}
                    {u.status !== "rejected" && u.id !== user?.id && (
                      <IconBtn
                        testid={`reject-${u.id}`}
                        onClick={() =>
                          act(() => adminRejectUser(u.id), "Rejected")
                        }
                        title="Reject"
                        color="#ff3b30"
                      >
                        <X className="h-3.5 w-3.5" />
                      </IconBtn>
                    )}
                    {u.role !== "admin" && u.status === "approved" && (
                      <IconBtn
                        testid={`promote-${u.id}`}
                        onClick={() =>
                          act(() => adminSetRole(u.id, "admin"), "Promoted to admin")
                        }
                        title="Promote to admin"
                        color="#00f0ff"
                      >
                        <ShieldCheck className="h-3.5 w-3.5" />
                      </IconBtn>
                    )}
                    {u.role === "admin" && u.id !== user?.id && (
                      <IconBtn
                        testid={`demote-${u.id}`}
                        onClick={() =>
                          act(() => adminSetRole(u.id, "user"), "Demoted to user")
                        }
                        title="Demote to user"
                        color="#ffb800"
                      >
                        <UserIcon className="h-3.5 w-3.5" />
                      </IconBtn>
                    )}
                    {u.id !== user?.id && (
                      <IconBtn
                        testid={`delete-${u.id}`}
                        onClick={() => {
                          if (window.confirm("Delete this user?"))
                            act(() => adminDeleteUser(u.id), "Deleted");
                        }}
                        title="Delete"
                        color="#ff3b30"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </IconBtn>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function IconBtn({ children, onClick, title, color, testid }) {
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      title={title}
      className="border border-[#2a2a2a] p-1.5 text-neutral-400 transition-colors"
      style={{
        transition: "all 120ms",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.color = color;
        e.currentTarget.style.borderColor = color;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.color = "";
        e.currentTarget.style.borderColor = "";
      }}
    >
      {children}
    </button>
  );
}
