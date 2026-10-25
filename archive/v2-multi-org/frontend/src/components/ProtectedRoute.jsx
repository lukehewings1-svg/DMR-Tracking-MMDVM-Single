import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { isAdmin, isSuperAdmin } from "@/lib/api";

export function ProtectedRoute({ children, adminOnly = false, superOnly = false }) {
  const { user } = useAuth();
  if (user === undefined) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#050505] mono text-xs text-neutral-500">
        // authenticating…
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (superOnly && !isSuperAdmin(user)) return <Navigate to="/" replace />;
  if (adminOnly && !isAdmin(user)) return <Navigate to="/" replace />;
  return children;
}
