"""DMR voice framing: build/parse the 33-byte bursts carried in HomeBrew DMRD packets."""
from __future__ import annotations

from bitarray import bitarray
from dmr_utils3 import ambe_utils, bptc, const, golay, qr

DT_VOICE_HEAD = 1
DT_VOICE_TERM = 2
FT_VOICE, FT_VOICE_SYNC, FT_DATA_SYNC = 0, 1, 2
_LCSS = {1: 1, 2: 3, 3: 3, 4: 2}  # bursts B..E carry first/continue/continue/last


def full_lc(private: bool, dst: int, src: int) -> bytes:
    return bytes([0x03 if private else 0x00, 0, 0]) + dst.to_bytes(3, "big") + src.to_bytes(3, "big")


def _bits(data: bytes) -> bitarray:
    b = bitarray(endian="big")
    b.frombytes(bytes(data))
    return b


def _slot_type(cc: int, dtype: int) -> bitarray:
    return _bits(golay.encode_2087(bytes([((cc & 0xF) << 4) | dtype])).to_bytes(3, "big"))[4:]


def _emb(cc: int, lcss: int) -> bitarray:
    return _bits(qr.encode(bytearray([((cc & 0xF) << 4) | ((lcss & 3) << 1), 0])))


def dmrd(seq: int, src: int, dst: int, rpt: int, slot: int, private: bool, ftype: int, dtype: int, stream_id: int, payload: bytes) -> bytes:
    bits = (0x80 if slot == 2 else 0) | (0x40 if private else 0) | (ftype << 4) | (dtype & 0xF)
    return (
        b"DMRD" + bytes([seq & 0xFF]) + src.to_bytes(3, "big") + dst.to_bytes(3, "big")
        + rpt.to_bytes(4, "big") + bytes([bits]) + stream_id.to_bytes(4, "big") + payload
    )


class VoiceStreamEncoder:
    """Turns AMBE frames into a header, A-F voice superframes and a terminator."""

    def __init__(self, src: int, dst: int, private: bool, cc: int = 1):
        lc = full_lc(private, dst, src)
        self.cc = cc
        self._head = bptc.encode_header_lc(lc)
        self._term = bptc.encode_terminator_lc(lc)
        self._emb_lc = bptc.encode_emblc(lc)
        self.n = 0

    def _data_burst(self, info: bitarray, dtype: int) -> bytes:
        st = _slot_type(self.cc, dtype)
        return (info[0:98] + st[0:10] + const.BS_DATA_SYNC + st[10:20] + info[98:196]).tobytes()

    def header(self) -> bytes:
        return self._data_burst(self._head, DT_VOICE_HEAD)

    def terminator(self) -> bytes:
        return self._data_burst(self._term, DT_VOICE_TERM)

    def voice(self, ambe49: list[bitarray]) -> tuple[bytes, int]:
        """Three 49-bit AMBE frames -> (33-byte burst, vseq 0..5)."""
        vseq = self.n % 6
        self.n += 1
        a = bitarray(endian="big")
        for f in ambe49:
            a.frombytes(bytes(ambe_utils.convert49BitTo72BitAMBE(f)))
        if vseq == 0:
            mid = const.BS_VOICE_SYNC
        elif vseq in _LCSS:
            e = _emb(self.cc, _LCSS[vseq])
            mid = e[0:8] + self._emb_lc[vseq] + e[8:16]
        else:
            e = _emb(self.cc, 0)
            mid = e[0:8] + bitarray("0" * 32) + e[8:16]
        return (a[0:108] + mid + a[108:216]).tobytes(), vseq


def extract_ambe49(payload: bytes) -> list[bitarray]:
    """33-byte voice burst -> three 49-bit AMBE frames."""
    b = _bits(payload[:33])
    frames = [b[0:72], b[72:108] + b[156:192], b[192:264]]
    return [ambe_utils.convert72BitTo49BitAMBE(f) for f in frames]
