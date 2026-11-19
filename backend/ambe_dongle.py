"""DVSI AMBE-3000 (DV3000 / ThumbDV) serial driver: PCM <-> 49-bit AMBE+2 frames."""
from __future__ import annotations

import threading
from array import array
from typing import Optional

from bitarray import bitarray

START = 0x61
RATE_INDEX = 34  # AMBE+2 2450 bps, no FEC (DMR FEC is added in dmr_voice)


class AmbeDongle:
    def __init__(self, path: Optional[str], baud: int = 460800):
        self.path = path
        self.baud = baud
        self.ser = None
        self.product: Optional[str] = None
        self.error: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def ok(self) -> bool:
        return self.ser is not None

    def open(self) -> None:
        if not self.path:
            self.error = "AMBE_DEVICE_PATH not set"
            return
        try:
            import serial

            self.ser = serial.Serial(self.path, self.baud, timeout=1)
            self._xfer(bytes([0x00, 0x33]), 0x00)  # reset -> READY
            prod = self._xfer(bytes([0x00, 0x30]), 0x00)  # product id
            self.product = prod[1:].split(b"\x00")[0].decode(errors="ignore") or "AMBE-3000"
            self._xfer(bytes([0x00, 0x09, RATE_INDEX]), 0x00)
            self.error = None
        except Exception as exc:  # noqa: BLE001
            self.error = f"AMBE dongle error: {exc}"
            self.close()

    def close(self) -> None:
        if self.ser:
            try:
                self.ser.close()
            except Exception:  # noqa: BLE001
                pass
        self.ser = None

    def _xfer(self, body: bytes, expect_type: int) -> bytes:
        """body = type byte + fields. Returns the response fields."""
        pkt = bytes([START]) + (len(body) - 1).to_bytes(2, "big") + body
        with self._lock:
            self.ser.reset_input_buffer()
            self.ser.write(pkt)
            head = self.ser.read(4)
            if len(head) < 4 or head[0] != START:
                raise IOError("no response from AMBE dongle")
            n = int.from_bytes(head[1:3], "big")
            data = self.ser.read(n)
        if head[3] != expect_type or len(data) < n:
            raise IOError("unexpected AMBE response")
        return data

    def encode(self, pcm_le: bytes) -> bitarray:
        """320 bytes PCM16LE @ 8 kHz (20 ms) -> 49-bit frame."""
        s = array("h", pcm_le)
        s.byteswap()
        data = self._xfer(bytes([0x02, 0x00, 160]) + s.tobytes(), 0x01)
        b = bitarray(endian="big")
        b.frombytes(data[2:9])
        return b[:49]

    def decode(self, ambe49: bitarray) -> bytes:
        bits = ambe49 + bitarray("0" * (56 - len(ambe49)))
        data = self._xfer(bytes([0x01, 0x01, 49]) + bits.tobytes(), 0x02)
        s = array("h", data[2 : 2 + 320])
        s.byteswap()
        return s.tobytes()

    def status(self) -> dict:
        return {"configured": bool(self.path), "ok": self.ok, "path": self.path, "product": self.product, "error": self.error}
