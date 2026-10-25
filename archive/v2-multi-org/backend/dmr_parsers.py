"""
Multi-brand DMR GPS payload parsers.

Since raw DMR frames are heavily encoded (BPTC 196,96 FEC + interleaving), and the goal is
to remain protocol-agnostic across radio brands, we run every incoming reassembled data
payload through several parsers and take the first one that produces a valid coordinate.

Supported formats:
  * Motorola LRRP (Location Request/Response Protocol) - proprietary but well documented.
  * Hytera RRS/GPS   - proprietary Hytera GPS reports.
  * NMEA over DMR    - ($GPRMC / $GPGGA sentences some radios send verbatim).
  * APRS text        - Anytone, BTECH, TYT and others encode APRS position payloads in
                       DMR SMS/data slots.

Every parser accepts raw bytes and returns a dict with:
    { "format": str, "lat": float, "lon": float, "speed": float|None,
      "heading": float|None, "extra": dict }
or None if the payload does not match.
"""
from __future__ import annotations

import re
import struct
from typing import Optional, Dict, Any, List


# --------------------------------------------------------------------------- #
# Motorola LRRP
# --------------------------------------------------------------------------- #
# LRRP position report typically contains a Type-Length-Value stream. The
# coordinate TLV uses tag 0x51 (ImmediateLocationReport) or 0x55 (TriggeredLocationReport)
# followed by lat/lon as signed 32-bit fixed-point in units of (180/2^31) degrees.
_LRRP_LAT_LON_SCALE = 180.0 / (2 ** 31)
_LRRP_TAGS = (b"\x51", b"\x55", b"\x22", b"\x63", b"\x67")


def parse_lrrp(payload: bytes) -> Optional[Dict[str, Any]]:
    for tag in _LRRP_TAGS:
        idx = payload.find(tag)
        if idx == -1 or idx + 12 > len(payload):
            continue
        # walk forward looking for a plausible lat/lon big-endian pair
        for off in range(idx, min(idx + 24, len(payload) - 8)):
            try:
                lat_raw, lon_raw = struct.unpack(">ii", payload[off : off + 8])
            except struct.error:
                continue
            lat = lat_raw * _LRRP_LAT_LON_SCALE
            lon = lon_raw * _LRRP_LAT_LON_SCALE
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0 and (lat, lon) != (0.0, 0.0):
                return {
                    "format": "Motorola LRRP",
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "speed": None,
                    "heading": None,
                    "extra": {"tag": tag.hex()},
                }
    return None


# --------------------------------------------------------------------------- #
# Hytera RRS / GPS
# --------------------------------------------------------------------------- #
# Hytera's GPS trigger report encodes latitude and longitude as ASCII decimal
# degrees inside a wrapped protobuf-like structure. A common signature is the
# ASCII prefix "$P" or the token "GPS" followed by comma separated fields.
_HYTERA_RE = re.compile(
    rb"(?P<lat>-?\d{1,3}\.\d{3,6})[,;]\s*(?P<lon>-?\d{1,3}\.\d{3,6})"
)


def parse_hytera(payload: bytes) -> Optional[Dict[str, Any]]:
    if b"HYT" not in payload and b"$P" not in payload and b"GPS" not in payload:
        return None
    m = _HYTERA_RE.search(payload)
    if not m:
        return None
    try:
        lat = float(m.group("lat"))
        lon = float(m.group("lon"))
    except ValueError:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return {
        "format": "Hytera RRS",
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "speed": None,
        "heading": None,
        "extra": {},
    }


# --------------------------------------------------------------------------- #
# NMEA over DMR
# --------------------------------------------------------------------------- #
_NMEA_RE = re.compile(rb"\$(GP|GN|GL)(RMC|GGA|GLL)[^\r\n$]*")


def _nmea_to_decimal(coord: str, hemi: str) -> Optional[float]:
    if not coord or "." not in coord:
        return None
    dot = coord.index(".")
    deg_len = dot - 2
    if deg_len <= 0:
        return None
    try:
        deg = int(coord[:deg_len])
        minutes = float(coord[deg_len:])
    except ValueError:
        return None
    val = deg + minutes / 60.0
    if hemi in ("S", "W"):
        val = -val
    return val


def parse_nmea(payload: bytes) -> Optional[Dict[str, Any]]:
    m = _NMEA_RE.search(payload)
    if not m:
        return None
    sentence = m.group(0).decode("ascii", errors="ignore")
    parts = sentence.split(",")
    lat = lon = speed = heading = None
    try:
        if parts[0].endswith("RMC") and len(parts) >= 9:
            lat = _nmea_to_decimal(parts[3], parts[4])
            lon = _nmea_to_decimal(parts[5], parts[6])
            speed = float(parts[7]) * 1.852 if parts[7] else None  # knots -> km/h
            heading = float(parts[8]) if parts[8] else None
        elif parts[0].endswith("GGA") and len(parts) >= 6:
            lat = _nmea_to_decimal(parts[2], parts[3])
            lon = _nmea_to_decimal(parts[4], parts[5])
        elif parts[0].endswith("GLL") and len(parts) >= 5:
            lat = _nmea_to_decimal(parts[1], parts[2])
            lon = _nmea_to_decimal(parts[3], parts[4])
    except (ValueError, IndexError):
        return None
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return {
        "format": "NMEA",
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "speed": round(speed, 2) if speed else None,
        "heading": round(heading, 1) if heading else None,
        "extra": {"sentence": sentence},
    }


# --------------------------------------------------------------------------- #
# APRS text over DMR
# --------------------------------------------------------------------------- #
_APRS_RE = re.compile(
    rb"[!=/@]"
    rb"(?P<lat>\d{4}\.\d{2})"
    rb"(?P<ns>[NS])"
    rb"[\\/A-Za-z0-9]"
    rb"(?P<lon>\d{5}\.\d{2})"
    rb"(?P<ew>[EW])"
)


# --------------------------------------------------------------------------- #
# Emergency alarm detection
# --------------------------------------------------------------------------- #
# Different brands signal emergency differently:
#   * Motorola: CSBKO 0x24 (EmergencyAlarm), payload contains "EMER" ASCII tag
#     in some MOTOTRBO variants; the frame's FLCO carries FLCO=6.
#   * Hytera: broadcasts an emergency data burst with tag 0xB0 in the PDU
#     preamble.
#   * Generic: many radios send the ASCII substring "EMERGENCY" or "EMER" as
#     part of the alarm payload for interoperability.
# We match any of these signatures - detection tolerates false positives on the
# frontend by showing the user which radio + when.
_EMERGENCY_TAGS = (b"EMERGENCY", b"EMER", b"\xb0\x00\x00", b"\x24\xa0")


def parse_emergency(payload: bytes) -> Optional[Dict[str, Any]]:
    if not payload:
        return None
    for tag in _EMERGENCY_TAGS:
        if tag in payload:
            return {"type": "emergency_alarm", "signature": tag.hex()}
    return None


def parse_aprs(payload: bytes) -> Optional[Dict[str, Any]]:
    m = _APRS_RE.search(payload)
    if not m:
        return None
    lat = _nmea_to_decimal(m.group("lat").decode(), m.group("ns").decode())
    lon = _nmea_to_decimal(m.group("lon").decode(), m.group("ew").decode())
    if lat is None or lon is None:
        return None
    return {
        "format": "APRS",
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "speed": None,
        "heading": None,
        "extra": {},
    }


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
_PARSERS = (parse_lrrp, parse_hytera, parse_nmea, parse_aprs)


def parse_gps_payload(payload: bytes) -> Optional[Dict[str, Any]]:
    """Try every registered parser; return the first successful decode."""
    for fn in _PARSERS:
        try:
            result = fn(payload)
        except Exception:  # noqa: BLE001 - parsers must never crash the ingest loop
            continue
        if result:
            return result
    return None


def parser_names() -> List[str]:
    return ["Motorola LRRP", "Hytera RRS", "NMEA", "APRS"]
