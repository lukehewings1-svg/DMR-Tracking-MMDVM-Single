import { useEffect, useRef, useState } from "react";
import { Play, Square, Zap } from "lucide-react";
import { injectPacket, injectRawHex } from "@/lib/api";
import { toast } from "sonner";

// A handful of pretend radios roaming around different regions of the world.
const MOCK_RADIOS = [
  { dmr_id: 3126001, callsign: "K7SAR-1", format: "Motorola LRRP", lat: 47.6062, lon: -122.3321 },
  { dmr_id: 2621452, callsign: "DL7ABC", format: "Hytera RRS", lat: 52.5200, lon: 13.4050 },
  { dmr_id: 3110099, callsign: "N0GPS", format: "NMEA", lat: 39.7392, lon: -104.9903 },
  { dmr_id: 5057231, callsign: "VK3QRP", format: "APRS", lat: -37.8136, lon: 144.9631 },
  { dmr_id: 3021777, callsign: "VE3TAC", format: "Motorola LRRP", lat: 43.6532, lon: -79.3832 },
];

// Prebaked hex payloads that our parsers know how to decode. Real MMDVM packets
// look similar - this lets the raw-hex demo prove the parser stack works.
const RAW_SAMPLES = [
  {
    label: "LRRP fix (Motorola)",
    dmr_id: 3126555,
    // tag 0x51 + lat/lon big-endian 32-bit (47.6062, -122.3321)
    hex: "51" + toBEHex(47.6062) + toBEHex(-122.3321),
  },
  {
    label: "NMEA $GPRMC",
    dmr_id: 3110888,
    hex: strToHex(
      "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"
    ),
  },
  {
    label: "APRS !DDMM position",
    dmr_id: 5058881,
    hex: strToHex("!3745.60N/12225.90W>Test packet"),
  },
  {
    label: "Hytera GPS report",
    dmr_id: 2621777,
    hex: strToHex("HYT$GPS,52.5192,13.4061,SAT8"),
  },
];

function toBEHex(deg) {
  const raw = Math.round(deg / (180 / 2 ** 31));
  const u = raw < 0 ? raw + 2 ** 32 : raw;
  return u.toString(16).padStart(8, "0");
}
function strToHex(s) {
  return Array.from(new TextEncoder().encode(s))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
function jitter(v, r = 0.02) {
  return v + (Math.random() - 0.5) * r;
}

export function Injector({ onSent }) {
  const [running, setRunning] = useState(false);
  const [rate, setRate] = useState(2000);
  const stateRef = useRef(MOCK_RADIOS.map((r) => ({ ...r })));

  useEffect(() => {
    if (!running) return;
    const id = setInterval(async () => {
      const radio = stateRef.current[
        Math.floor(Math.random() * stateRef.current.length)
      ];
      radio.lat = jitter(radio.lat, 0.03);
      radio.lon = jitter(radio.lon, 0.03);
      try {
        await injectPacket({
          dmr_id: radio.dmr_id,
          callsign: radio.callsign,
          lat: Number(radio.lat.toFixed(6)),
          lon: Number(radio.lon.toFixed(6)),
          format: radio.format,
          speed: Number((10 + Math.random() * 60).toFixed(1)),
          heading: Math.round(Math.random() * 359),
          rssi: -60 - Math.round(Math.random() * 40),
        });
        onSent?.();
      } catch {
        /* noop */
      }
    }, rate);
    return () => clearInterval(id);
  }, [running, rate, onSent]);

  const singleShot = async () => {
    const radio = stateRef.current[Math.floor(Math.random() * stateRef.current.length)];
    radio.lat = jitter(radio.lat, 0.05);
    radio.lon = jitter(radio.lon, 0.05);
    await injectPacket({
      dmr_id: radio.dmr_id,
      callsign: radio.callsign,
      lat: Number(radio.lat.toFixed(6)),
      lon: Number(radio.lon.toFixed(6)),
      format: radio.format,
      speed: Number((10 + Math.random() * 60).toFixed(1)),
      heading: Math.round(Math.random() * 359),
      rssi: -60 - Math.round(Math.random() * 40),
    });
    onSent?.();
    toast.success(`Injected ${radio.callsign}`);
  };

  const sendRaw = async (sample) => {
    const res = await injectRawHex({
      dmr_id: sample.dmr_id,
      callsign: sample.label,
      hex: sample.hex,
    });
    if (res.ok) {
      toast.success(`Parsed as ${res.format}`);
      onSent?.();
    } else {
      toast.error(res.error || "Parser did not match");
    }
  };

  return (
    <div data-testid="injector" className="border-b border-[#2a2a2a] p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">
          Simulated GPS Injector
        </div>
        <div className="mono text-[10px] text-neutral-500">
          {stateRef.current.length} mock radios
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          data-testid="injector-toggle"
          onClick={() => setRunning((r) => !r)}
          className={`flex items-center gap-1.5 border px-3 py-1.5 mono text-[11px] uppercase tracking-wider transition-colors ${
            running
              ? "border-[#ff3b30] bg-[#1a0505] text-[#ff3b30] hover:bg-[#2a0808]"
              : "border-[#39ff14] bg-[#0a1a0a] text-[#39ff14] hover:bg-[#102a10]"
          }`}
        >
          {running ? <Square className="h-3 w-3" /> : <Play className="h-3 w-3" />}
          {running ? "Stop" : "Start Stream"}
        </button>

        <button
          data-testid="injector-single"
          onClick={singleShot}
          className="flex items-center gap-1.5 border border-[#2a2a2a] px-3 py-1.5 mono text-[11px] uppercase tracking-wider text-neutral-300 transition-colors hover:border-[#00f0ff] hover:text-[#00f0ff]"
        >
          <Zap className="h-3 w-3" />
          One Fix
        </button>

        <div className="flex items-center gap-2 mono text-[10px] text-neutral-500">
          <span>RATE</span>
          <select
            data-testid="injector-rate"
            value={rate}
            onChange={(e) => setRate(Number(e.target.value))}
            className="border border-[#2a2a2a] bg-black px-1 py-0.5 text-neutral-200 outline-none"
          >
            <option value={500}>500ms</option>
            <option value={1000}>1s</option>
            <option value={2000}>2s</option>
            <option value={5000}>5s</option>
          </select>
        </div>
      </div>

      <div className="mt-3">
        <div className="mb-1 text-[10px] uppercase tracking-[0.25em] text-neutral-600">
          Raw-hex parser tests
        </div>
        <div className="grid grid-cols-2 gap-1">
          {RAW_SAMPLES.map((s) => (
            <button
              key={s.label}
              data-testid={`raw-sample-${s.label.replace(/\s+/g, "-").toLowerCase()}`}
              onClick={() => sendRaw(s)}
              className="border border-[#2a2a2a] px-2 py-1 text-left mono text-[10px] text-neutral-300 transition-colors hover:border-[#39ff14] hover:text-[#39ff14]"
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
