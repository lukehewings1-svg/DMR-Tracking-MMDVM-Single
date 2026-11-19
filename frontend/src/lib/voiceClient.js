import { voiceWsUrl } from "@/lib/api";

// One shared voice connection per browser tab. Audio: PCM16LE 8 kHz, 20 ms frames.
const RATE = 8000;
const FRAME_SAMPLES = 160;

class VoiceClient {
  state = { connected: false, status: null, tx: "idle", rx: null, listening: false, volume: 0.8, error: null };
  listeners = new Set();
  ws = null;
  ctx = null;
  gain = null;
  playAt = 0;
  mic = null;
  pending = null;
  retry = null;

  subscribe(fn) {
    this.listeners.add(fn);
    fn(this.state);
    if (!this.ws) this.connect();
    return () => this.listeners.delete(fn);
  }

  set(patch) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((fn) => fn(this.state));
  }

  connect() {
    clearTimeout(this.retry);
    const ws = new WebSocket(voiceWsUrl());
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () => this.set({ connected: true });
    ws.onclose = () => {
      this.ws = null;
      this.set({ connected: false, rx: null });
      if (this.state.tx !== "idle") this.stopMic();
      this.retry = setTimeout(() => this.listeners.size && this.connect(), 4000);
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") return this.play(ev.data);
      const m = JSON.parse(ev.data);
      if (m.type === "voice_status") this.set({ status: m.status });
      else if (m.type === "rx_start") this.set({ rx: m });
      else if (m.type === "rx_end") this.set({ rx: null });
      else if (m.type === "ptt_granted") this.pending?.resolve(m);
      else if (m.type === "ptt_denied") {
        if (this.pending) this.pending.reject(new Error(m.reason));
        else if (this.state.tx === "live") {
          this.stopMic();
          this.set({ error: m.reason });
        }
      }
    };
  }

  ensureAudio() {
    if (!this.ctx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      this.ctx = new Ctx();
      this.gain = this.ctx.createGain();
      this.gain.gain.value = this.state.volume;
      this.gain.connect(this.ctx.destination);
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
    return this.ctx;
  }

  setListening(on) {
    if (on) this.ensureAudio();
    this.set({ listening: on });
  }

  setVolume(v) {
    if (this.gain) this.gain.gain.value = v;
    this.set({ volume: v });
  }

  play(buf) {
    if (!this.state.listening || !this.ctx) return;
    const pcm = new Int16Array(buf);
    const ab = this.ctx.createBuffer(1, pcm.length, RATE);
    const ch = ab.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 32768;
    const src = this.ctx.createBufferSource();
    src.buffer = ab;
    src.connect(this.gain);
    const now = this.ctx.currentTime;
    if (this.playAt < now + 0.05 || this.playAt > now + 1) this.playAt = now + 0.15; // jitter buffer
    src.start(this.playAt);
    this.playAt += ab.duration;
  }

  async startTx(callType, targetId) {
    if (!this.ws || this.ws.readyState !== 1) throw new Error("Voice link not connected");
    if (this.state.tx !== "idle") return;
    this.set({ tx: "requesting", error: null });
    this.cancelled = false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const granted = new Promise((resolve, reject) => (this.pending = { resolve, reject }));
      this.ws.send(JSON.stringify({ type: "ptt_start", call_type: callType, target_id: targetId }));
      const g = await Promise.race([granted, new Promise((_, r) => setTimeout(() => r(new Error("No answer from server")), 4000))]);
      this.pending = null;
      if (this.cancelled) {
        stream.getTracks().forEach((t) => t.stop());
        this.ws.send(JSON.stringify({ type: "ptt_end" }));
        this.set({ tx: "idle" });
        return g;
      }
      this.startMic(stream);
      this.set({ tx: "live", route: g.route });
      return g;
    } catch (e) {
      this.pending = null;
      this.set({ tx: "idle" });
      throw e;
    }
  }

  startMic(stream) {
    const ctx = this.ensureAudio();
    const source = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(2048, 1, 1);
    const ratio = ctx.sampleRate / RATE;
    let carry = [];
    let pos = 0;
    proc.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      for (; pos < input.length; pos += ratio) carry.push(input[Math.floor(pos)]);
      pos -= input.length;
      while (carry.length >= FRAME_SAMPLES) {
        const out = new Int16Array(FRAME_SAMPLES);
        for (let i = 0; i < FRAME_SAMPLES; i++) out[i] = Math.max(-1, Math.min(1, carry[i])) * 32767;
        carry = carry.slice(FRAME_SAMPLES);
        if (this.ws?.readyState === 1) this.ws.send(out.buffer);
      }
    };
    const sink = ctx.createGain();
    sink.gain.value = 0;
    source.connect(proc);
    proc.connect(sink);
    sink.connect(ctx.destination);
    this.mic = { stream, source, proc, sink };
  }

  stopMic() {
    const m = this.mic;
    if (m) {
      m.proc.disconnect();
      m.source.disconnect();
      m.sink.disconnect();
      m.stream.getTracks().forEach((t) => t.stop());
    }
    this.mic = null;
    this.set({ tx: "idle" });
  }

  stopTx() {
    if (this.state.tx === "idle") return;
    if (this.state.tx === "requesting") {
      this.cancelled = true;
      return;
    }
    this.stopMic();
    if (this.ws?.readyState === 1) this.ws.send(JSON.stringify({ type: "ptt_end" }));
  }
}

export const voiceClient = new VoiceClient();
