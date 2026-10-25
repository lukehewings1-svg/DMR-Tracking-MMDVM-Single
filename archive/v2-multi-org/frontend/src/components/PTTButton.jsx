import { useRef, useState } from "react";
import { Mic, MicOff, Radio, MessageSquare } from "lucide-react";
import { voiceStatus, voicePtt, sendMessage } from "@/lib/api";
import { toast } from "sonner";

/**
 * PTT (push-to-talk) button. Requires an AMBE hardware dongle attached to the
 * server. When unavailable, the button falls back to sending a DMR text message
 * with the caller's callsign so the target radio still knows someone is trying
 * to reach them.
 */
export function PTTButton({ targetDmrId, groupId, groupName, callerCallsign }) {
  const [hw, setHw] = useState(null);
  const [pressing, setPressing] = useState(false);
  const mediaRef = useRef(null);

  const ensureStatus = async () => {
    if (hw) return hw;
    const s = await voiceStatus();
    setHw(s);
    return s;
  };

  const onPress = async () => {
    const s = await ensureStatus();
    if (!s.ambe_hardware_available) {
      // Fallback: send a "please call in" SMS
      const text = `[${callerCallsign || "control"}] Requesting voice contact on ${
        groupId ? `group ${groupName}` : `ID ${targetDmrId}`
      }`;
      try {
        await sendMessage(
          targetDmrId ? { text, target_dmr_id: targetDmrId } : { text, group_id: groupId }
        );
        toast(`AMBE dongle not detected - sent DMR text instead`, {
          description: s.reason,
          duration: 5000,
        });
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Fallback SMS failed");
      }
      return;
    }
    // AMBE available: begin PTT session
    setPressing(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRef.current = stream;
      await voicePtt({ target_dmr_id: targetDmrId, group_id: groupId });
      toast.success(`Transmitting to ${groupId ? groupName : `ID ${targetDmrId}`}`);
    } catch (e) {
      toast.error("Microphone unavailable");
      setPressing(false);
    }
  };

  const onRelease = () => {
    if (mediaRef.current) {
      mediaRef.current.getTracks().forEach((t) => t.stop());
      mediaRef.current = null;
    }
    setPressing(false);
  };

  const hardwareOk = hw?.ambe_hardware_available;
  const label = groupId ? `Talk to ${groupName || "group"}` : "Private call";

  return (
    <div className="space-y-1" data-testid="ptt-container">
      <button
        data-testid="ptt-button"
        onMouseDown={onPress}
        onMouseUp={onRelease}
        onMouseLeave={onRelease}
        onTouchStart={onPress}
        onTouchEnd={onRelease}
        className={`flex w-full items-center justify-center gap-2 border px-3 py-2 mono text-[11px] uppercase tracking-widest transition-colors ${
          pressing
            ? "border-[#ff3b30] bg-[#ff3b30] text-black"
            : hardwareOk === false
            ? "border-[#ffb800] bg-[#1a1005] text-[#ffb800] hover:bg-[#ffb800] hover:text-black"
            : "border-[#39ff14] bg-[#0a1a0a] text-[#39ff14] hover:bg-[#39ff14] hover:text-black"
        }`}
      >
        {hardwareOk === false ? (
          <>
            <MessageSquare className="h-3.5 w-3.5" />
            {label} (SMS fallback)
          </>
        ) : pressing ? (
          <>
            <Mic className="h-3.5 w-3.5" /> TRANSMITTING…
          </>
        ) : (
          <>
            <Mic className="h-3.5 w-3.5" /> {label}
          </>
        )}
      </button>
      {hardwareOk === false && (
        <div className="mono text-[9px] leading-snug text-neutral-500">
          AMBE dongle not detected on server. Plug a DV3000/ThumbDV into this
          machine and set AMBE_DEVICE_PATH in backend/.env to enable live PTT.
          Falling back to DMR text message.
        </div>
      )}
    </div>
  );
}
