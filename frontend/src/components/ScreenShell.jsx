import { LogOut } from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { ScreenNav } from "@/components/ScreenNav";
import { EmergencyBanner } from "@/components/EmergencyBanner";
import { useAuth } from "@/context/AuthContext";

// Shared header for the Dispatch and Admin screens.
export function ScreenShell({ live, testid, title, onEmergencyFocus, actions, children }) {
  const { user, signOut } = useAuth();
  return (
    <div data-testid={testid} className="flex h-screen w-screen flex-col overflow-hidden bg-[#050505]">
      <TopBar status={live.status} connected={live.connected} lastEventAt={live.lastEventAt} />
      <div className="flex items-center justify-between gap-2 border-b border-[#2a2a2a] bg-[#0a0a0a] px-2 py-1.5 mono text-[11px] md:px-4">
        <div className="flex min-w-0 items-center gap-3">
          <ScreenNav />
          <span className="hidden truncate uppercase tracking-[0.3em] text-neutral-500 md:inline">{title}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {actions}
          <span className="hidden truncate text-neutral-400 md:inline">{user?.email}</span>
          <button
            data-testid="shell-signout"
            onClick={signOut}
            title="Sign out"
            className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 text-neutral-300 hover:border-[#ff3b30] hover:text-[#ff3b30]"
          >
            <LogOut className="h-3 w-3" />
          </button>
        </div>
      </div>
      <EmergencyBanner emergencies={live.emergencies} onFocus={onEmergencyFocus} onCleared={live.refreshAll} />
      {children}
    </div>
  );
}
