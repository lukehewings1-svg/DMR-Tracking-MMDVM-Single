import { Radio, Wifi, WifiOff, Building2 } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

export function TopBar({ status, connected, lastEventAt, user }) {
  const listener = status?.listener;
  const running = !!listener?.running;
  const stats = listener?.stats;

  return (
    <header
      data-testid="topbar"
      className="flex items-center justify-between border-b border-[#2a2a2a] bg-[#050505] px-4 py-2"
    >
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center border border-[#39ff14] text-[#39ff14]">
          <Radio className="h-4 w-4" />
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.3em] text-neutral-500">
            DMR TRACKER
          </div>
          <div className="mono text-xs text-neutral-300">
            HOMEBREW MASTER · MULTI-ORG
          </div>
        </div>
        {user?.org_name && (
          <div
            data-testid="org-badge"
            className="ml-2 flex items-center gap-1 border border-[#00f0ff]/40 bg-[#00f0ff]/10 px-2 py-1 mono text-[10px] uppercase tracking-widest text-[#00f0ff]"
            title={user.role === "super_admin" ? "You are a super admin" : `Your organization: ${user.org_name}`}
          >
            <Building2 className="h-3 w-3" />
            {user.org_name}
            {user.role === "super_admin" && (
              <span className="ml-1 border-l border-[#00f0ff]/40 pl-1 text-[#ffb800]">
                SUPER
              </span>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-6 mono text-[11px]">
        <Metric
          label="LISTENER"
          value={listener ? listener.bind : "…"}
          state={running ? "ok" : "warn"}
          testid="metric-listener"
        />
        <Metric
          label="REPEATERS"
          value={stats?.repeaters_online ?? 0}
          state={(stats?.repeaters_online ?? 0) > 0 ? "ok" : "idle"}
          testid="metric-repeaters"
        />
        <Metric
          label="DMR FRAMES"
          value={stats?.dmr_frames ?? 0}
          state="idle"
          testid="metric-frames"
        />
        <Metric
          label="GPS FIXES"
          value={stats?.gps_decoded ?? 0}
          state={(stats?.gps_decoded ?? 0) > 0 ? "ok" : "idle"}
          testid="metric-fixes"
        />
        <Metric
          label="RADIOS"
          value={status?.radios_tracked ?? 0}
          state="idle"
          testid="metric-radios"
        />
        <div className="flex items-center gap-2" data-testid="ws-state">
          {connected ? (
            <>
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#39ff14] opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#39ff14]" />
              </span>
              <span className="text-[#39ff14]">LIVE</span>
            </>
          ) : (
            <>
              <WifiOff className="h-3.5 w-3.5 text-[#ff3b30]" />
              <span className="text-[#ff3b30]">OFFLINE</span>
            </>
          )}
        </div>
        {lastEventAt && (
          <div className="text-neutral-500">
            LAST PKT{" "}
            <span className="text-neutral-300">
              {formatDistanceToNow(lastEventAt, { addSuffix: true })}
            </span>
          </div>
        )}
      </div>
    </header>
  );
}

function Metric({ label, value, state, testid }) {
  const color =
    state === "ok"
      ? "text-[#39ff14]"
      : state === "warn"
      ? "text-[#ffb800]"
      : "text-neutral-200";
  return (
    <div className="flex flex-col items-start" data-testid={testid}>
      <span className="text-[9px] tracking-[0.25em] text-neutral-500">
        {label}
      </span>
      <span className={`mono ${color}`}>{value}</span>
    </div>
  );
}
