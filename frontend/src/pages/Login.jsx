import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiErrorMessage } from "@/lib/api";
import { Radio } from "lucide-react";

export default function Login() {
  const { signIn } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      await signIn(email.trim().toLowerCase(), password);
      nav("/");
    } catch (ex) {
      setErr(apiErrorMessage(ex));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid h-screen w-screen grid-cols-1 lg:grid-cols-[1fr_420px] bg-[#050505]">
      <SidePanel />
      <div className="flex items-center justify-center border-l border-[#2a2a2a] px-8">
        <form
          onSubmit={submit}
          data-testid="login-form"
          className="w-full max-w-sm"
        >
          <div className="mb-8">
            <div className="text-[10px] uppercase tracking-[0.4em] text-neutral-500">
              Access
            </div>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight text-neutral-100">
              Sign in
            </h1>
            <p className="mt-1 mono text-[11px] text-neutral-500">
              Operator credentials required.
            </p>
          </div>

          <label className="mb-3 block">
            <span className="mono text-[10px] uppercase tracking-widest text-neutral-500">
              Email
            </span>
            <input
              data-testid="login-email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full border border-[#2a2a2a] bg-black px-3 py-2 mono text-sm text-neutral-100 outline-none transition-colors focus:border-[#00f0ff]"
            />
          </label>

          <label className="mb-4 block">
            <span className="mono text-[10px] uppercase tracking-widest text-neutral-500">
              Password
            </span>
            <input
              data-testid="login-password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full border border-[#2a2a2a] bg-black px-3 py-2 mono text-sm text-neutral-100 outline-none transition-colors focus:border-[#00f0ff]"
            />
          </label>

          {err && (
            <div
              data-testid="login-error"
              className="mb-3 border border-[#ff3b30]/60 bg-[#1a0505] px-3 py-2 mono text-[11px] text-[#ff3b30]"
            >
              {err}
            </div>
          )}

          <button
            data-testid="login-submit"
            type="submit"
            disabled={loading}
            className="w-full border border-[#39ff14] bg-[#0a1a0a] px-4 py-2 mono text-xs uppercase tracking-[0.25em] text-[#39ff14] transition-colors hover:bg-[#39ff14] hover:text-black disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "authenticating…" : "Sign in →"}
          </button>

          <div className="mt-6 mono text-[11px] text-neutral-500">
            No account?{" "}
            <Link
              data-testid="to-register"
              to="/register"
              className="text-[#00f0ff] hover:underline"
            >
              Request access
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}

function SidePanel() {
  return (
    <div className="relative hidden lg:flex items-end justify-between overflow-hidden bg-[#050505] p-10">
      <div
        className="absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            "linear-gradient(#39ff14 1px, transparent 1px), linear-gradient(90deg, #39ff14 1px, transparent 1px)",
          backgroundSize: "24px 24px",
        }}
      />
      <div className="relative">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center border border-[#39ff14] text-[#39ff14]">
            <Radio className="h-5 w-5" />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.4em] text-neutral-500">
              DMR TRACKER
            </div>
            <div className="mono text-sm text-neutral-300">
              Off-network · HomeBrew Master
            </div>
          </div>
        </div>
        <h2 className="mt-16 max-w-md text-4xl font-semibold leading-tight tracking-tight text-neutral-100">
          Track every radio on your net,
          <br />
          in real time,
          <br />
          <span className="text-[#39ff14]">without a public link.</span>
        </h2>
        <p className="mt-4 max-w-md mono text-[11px] leading-relaxed text-neutral-500">
          A local HomeBrew master for your MMDVM. Decodes GPS from Motorola,
          Hytera, Anytone / BTECH and any brand emitting NMEA or APRS.
        </p>
      </div>

      <div className="relative mono text-[10px] uppercase tracking-[0.3em] text-neutral-600">
        v1.1 · UDP 62031 · OSM
      </div>
    </div>
  );
}
