import { useEffect, useRef, useState } from "react";
import { RefreshCw, Download, CheckCircle2, AlertTriangle } from "lucide-react";
import { formatDistanceToNowStrict } from "date-fns";
import { API, getUpdateStatus, applyUpdate, getUpdateJob } from "@/lib/api";

const btn = "flex items-center gap-1.5 border px-2 py-1 mono text-[10px] uppercase tracking-widest disabled:opacity-40";

async function waitForServerThenReload() {
  for (let i = 0; i < 120; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    try {
      const res = await fetch(`${API}/`, { cache: "no-store" });
      if (res.ok) return window.location.reload();
    } catch {
      /* still restarting */
    }
  }
}

export function UpdatePanel() {
  const [status, setStatus] = useState(null);
  const [checking, setChecking] = useState(false);
  const [job, setJob] = useState(null);
  const poll = useRef(null);

  const check = async () => {
    setChecking(true);
    try {
      setStatus(await getUpdateStatus());
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    check();
    return () => clearInterval(poll.current);
  }, []);

  const start = async () => {
    if (!window.confirm("Install the latest version now? The app restarts and is unavailable for about a minute.")) return;
    setJob(await applyUpdate());
    poll.current = setInterval(async () => {
      try {
        const j = await getUpdateJob();
        setJob(j);
        if (j.state === "restarting") {
          clearInterval(poll.current);
          waitForServerThenReload();
        } else if (j.state !== "running") clearInterval(poll.current);
      } catch {
        clearInterval(poll.current);
        waitForServerThenReload();
      }
    }, 2000);
  };

  const busy = job?.state === "running" || job?.state === "restarting";

  return (
    <div data-testid="update-panel" className="space-y-2 px-3 pb-3 mono text-[11px] text-neutral-300">
      {!status ? (
        <div className="text-neutral-500">// checking GitHub…</div>
      ) : !status.available ? (
        <div data-testid="update-unavailable" className="flex gap-2 text-[#ffb800]">
          <AlertTriangle className="h-4 w-4 shrink-0" /> {status.reason}
        </div>
      ) : (
        <>
          <div className="text-neutral-500">
            {status.remote} · {status.branch}
          </div>
          <div data-testid="update-current">
            Running <span className="text-neutral-100">{status.current.sha}</span> — {status.current.subject}
          </div>
          {status.behind === 0 ? (
            <div data-testid="update-up-to-date" className="flex items-center gap-1.5 text-[#39ff14]">
              <CheckCircle2 className="h-4 w-4" /> Up to date
            </div>
          ) : (
            <div data-testid="update-available" className="space-y-1">
              <div className="text-[#00f0ff]">{status.behind} update{status.behind === 1 ? "" : "s"} available:</div>
              <ul className="max-h-32 space-y-0.5 overflow-y-auto border-l border-[#2a2a2a] pl-2">
                {status.new_commits.map((c) => (
                  <li key={c.sha} className="text-neutral-200">
                    {c.subject} <span className="text-neutral-600">· {formatDistanceToNowStrict(new Date(c.date))} ago</span>
                  </li>
                ))}
              </ul>
              {status.local_changes && <div className="text-[#ffb800]">Files on this computer were edited by hand — the update may stop if they clash.</div>}
            </div>
          )}
        </>
      )}
      <div className="flex gap-2">
        <button data-testid="update-check" onClick={check} disabled={checking || busy} className={`${btn} border-[#2a2a2a] text-neutral-300 hover:border-[#00f0ff] hover:text-[#00f0ff]`}>
          <RefreshCw className={`h-3 w-3 ${checking ? "animate-spin" : ""}`} /> Check
        </button>
        {status?.available && status.behind > 0 && (
          <button data-testid="update-apply" onClick={start} disabled={busy} className={`${btn} border-[#39ff14] text-[#39ff14] hover:bg-[#39ff14] hover:text-black`}>
            <Download className="h-3 w-3" /> Update to latest
          </button>
        )}
      </div>
      {job && (
        <div data-testid="update-log" className="space-y-0.5 border border-[#2a2a2a] bg-black p-2 text-[10px]">
          {job.log.map((l, i) => (
            <div key={i} className="whitespace-pre-wrap text-neutral-400">{l}</div>
          ))}
          {job.state === "restarting" && <div className="text-[#00f0ff]">Waiting for the app to come back… this page reloads by itself.</div>}
          {job.state === "failed" && <div className="text-[#ff3b30]">Update stopped — nothing was restarted.</div>}
          {job.restart_needed_for_frontend && <div className="text-[#ffb800]">New dashboard packages were installed — close the app windows and start it again from the desktop icon.</div>}
        </div>
      )}
    </div>
  );
}
