"""Voice bridge + PTT stub.

* Voice bridging (radio -> radio across multiple MMDVMs): handled inside
  `dmr_ingest.HBMaster._handle_dmrd` - any DMRD frame on the voice slot is
  re-sent to every OTHER authenticated repeater session, turning the whole set
  of MMDVMs into a distributed simulcast for the transmitted talkgroup.

* PTT from a browser: requires a hardware AMBE encoder (DVSI DV3000 / ThumbDV)
  attached to the server via USB. `VoiceGateway` detects the dongle by env var
  `AMBE_DEVICE_PATH` and stores its status. When hardware isn't available the
  frontend automatically routes the "Talk" action to send a DMR SMS instead.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Awaitable, Callable, Optional


class VoiceGateway:
    def __init__(self):
        self.device_path: Optional[str] = os.environ.get("AMBE_DEVICE_PATH") or None
        self.hardware_available = bool(self.device_path and os.path.exists(self.device_path))
        # Voice activity tracker keyed by talkgroup_id
        # value: {"src_id", "callsign", "repeater_id", "last_at"}
        self._activity: dict[int, dict] = {}
        # per-repeater last transmit stats
        self._rpt_activity: dict[int, dict] = defaultdict(dict)

    def status(self) -> dict:
        return {
            "ambe_hardware_available": self.hardware_available,
            "ambe_device_path": self.device_path,
            "reason": None
            if self.hardware_available
            else "AMBE dongle not detected. Plug a DV3000/ThumbDV into the server and set AMBE_DEVICE_PATH in backend/.env.",
            "voice_activity": self.active_talkgroups(),
        }

    def track(
        self, talkgroup_id: int, src_id: int, callsign: Optional[str], repeater_id: int
    ) -> None:
        now = time.time()
        self._activity[talkgroup_id] = {
            "talkgroup_id": talkgroup_id,
            "src_id": src_id,
            "callsign": callsign,
            "repeater_id": repeater_id,
            "last_at": now,
        }
        self._rpt_activity[repeater_id] = {
            "talkgroup_id": talkgroup_id,
            "src_id": src_id,
            "last_at": now,
        }

    def active_talkgroups(self, ttl_sec: float = 2.0) -> list[dict]:
        now = time.time()
        out = []
        for tg, a in list(self._activity.items()):
            if now - a["last_at"] > ttl_sec:
                self._activity.pop(tg, None)
                continue
            out.append({**a, "age_ms": int((now - a["last_at"]) * 1000)})
        return out

    def transmit_from_browser(
        self, target_dmr_id: Optional[int], group_talkgroup: Optional[int]
    ) -> dict:
        """Placeholder for the AMBE encoder path.

        When hardware is available a full implementation would:
          1. Receive Opus/PCM from the browser (WebRTC or chunked POST).
          2. Resample to 8 kHz mono.
          3. Feed 20-ms frames into the AMBE dongle (DV3000 UART protocol).
          4. Emit DMRD voice frames toward every connected repeater with slot=
             VOICE_SLOT, correct call type + destination.

        For now we report status - the frontend falls back to SMS when no
        hardware is available.
        """
        if not self.hardware_available:
            return {
                "ok": False,
                "reason": "ambe_hardware_missing",
                "message": "AMBE dongle required. Plug a DV3000/ThumbDV into the server. "
                "The 'Talk' action will fall back to sending a DMR text message.",
            }
        return {
            "ok": True,
            "message": "AMBE stream endpoint reserved; real-time audio streaming "
            "will be added once a dongle is attached.",
            "target_dmr_id": target_dmr_id,
            "talkgroup_id": group_talkgroup,
        }
