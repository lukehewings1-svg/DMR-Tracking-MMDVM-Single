import { useEffect, useRef } from "react";
import { Mic, MessageSquare, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { sendMessage } from "@/lib/api";
import { voiceClient } from "@/lib/voiceClient";
import { useVoice } from "@/hooks/useVoice";

// Hold-to-talk. Live voice via the AMBE dongle or DMR818 gateway; when neither
// is available it sends a "please call in" DMR text instead.
export function PTTButton({ callType, targetId, groupId, label, callerCallsign, spaceKey = false, testid = "ptt-button" }) {
  const v = useVoice();
  const holding = useRef(false);
  const route = v.status?.route;
  const busyBy = v.status?.tx && v.tx === "idle" ? v.status.tx.user : null;

  const press = async () => {
    if (holding.current || !targetId) return;
    holding.current = true;
    if (!route) {
      holding.current = false;
      const text = `[${callerCallsign || "control"}] Please call in`;
      try {
        await sendMessage(callType === "private" ? { text, target_dmr_id: targetId } : { text, group_id: groupId });
        toast("No voice route - sent a DMR text instead", { description: "Connect an AMBE dongle or a DMR818 gateway for live voice." });
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Fallback text failed");
      }
      return;
    }
    try {
      await voiceClient.startTx(callType, targetId);
      if (!holding.current) voiceClient.stopTx();
    } catch (e) {
      holding.current = false;
      toast.error(e.message === "Permission denied" ? "Microphone blocked by the browser" : e.message);
    }
  };
  const release = () => {
    if (!holding.current) return;
    holding.current = false;
    voiceClient.stopTx();
  };

  useEffect(() => {
    if (!spaceKey) return;
    const typing = (e) => ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName) || e.target.isContentEditable;
    const down = (e) => {
      if (e.code === "Space" && !e.repeat && !typing(e)) {
        e.preventDefault();
        press();
      }
    };
    const up = (e) => {
      if (e.code === "Space" && !typing(e)) release();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  });

  const live = v.tx === "live";
  const cls = live
    ? "border-[#ff3b30] bg-[#ff3b30] text-black"
    : !route
    ? "border-[#ffb800] bg-[#1a1005] text-[#ffb800] hover:bg-[#ffb800] hover:text-black"
    : "border-[#39ff14] bg-[#0a1a0a] text-[#39ff14] hover:bg-[#39ff14] hover:text-black";

  return (
    <button
      data-testid={testid}
      disabled={!targetId || !!busyBy}
      onPointerDown={(e) => {
        try {
          e.currentTarget.setPointerCapture(e.pointerId);
        } catch {
          /* synthetic or touch pointer - fine without capture */
        }
        press();
      }}
      onPointerUp={release}
      onPointerCancel={release}
      onContextMenu={(e) => e.preventDefault()}
      className={`flex w-full select-none items-center justify-center gap-2 border-2 px-3 py-3 mono text-[12px] font-semibold uppercase tracking-widest transition-colors disabled:opacity-40 ${cls}`}
    >
      {v.tx === "requesting" ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : route ? (
        <Mic className="h-4 w-4" />
      ) : (
        <MessageSquare className="h-4 w-4" />
      )}
      {live ? "Transmitting… release to stop" : busyBy ? `${busyBy} is talking` : route ? `Hold to talk · ${label}` : `Send call-in text · ${label}`}
    </button>
  );
}
