import { Link, useLocation } from "react-router-dom";
import { LayoutGrid, Map as MapIcon, Headset, Settings2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const SCREENS = [
  { to: "/board", label: "Tracking Board", icon: MapIcon, testid: "screen-nav-board" },
  { to: "/dispatch", label: "Dispatch", icon: Headset, testid: "screen-nav-dispatch" },
  { to: "/admin", label: "Admin", icon: Settings2, testid: "screen-nav-admin", adminOnly: true },
  { to: "/", label: "All-in-one", icon: LayoutGrid, testid: "screen-nav-all" },
];

export function ScreenNav() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  return (
    <nav data-testid="screen-nav" className="flex shrink-0 items-center border border-[#2a2a2a] mono text-[10px] uppercase tracking-widest">
      {SCREENS.filter((s) => !s.adminOnly || isAdmin).map((s) => {
        const Icon = s.icon;
        const active = pathname === s.to;
        return (
          <Link
            key={s.to}
            to={s.to}
            data-testid={s.testid}
            title={s.label}
            className={`flex items-center gap-1.5 border-r border-[#2a2a2a] px-2 py-1 transition-colors last:border-r-0 ${
              active ? "bg-[#001a1f] text-[#00f0ff]" : "text-neutral-400 hover:bg-[#111] hover:text-neutral-100"
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            <span className="hidden lg:inline">{s.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
