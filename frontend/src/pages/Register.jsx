import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register, apiErrorMessage } from "@/lib/api";
import { Radio, CheckCircle2 } from "lucide-react";

export default function Register() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [callsign, setCallsign] = useState("");
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      await register({
        email: email.trim().toLowerCase(),
        password,
        callsign: callsign.trim() || null,
      });
      setSuccess(true);
    } catch (ex) {
      setErr(apiErrorMessage(ex));
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#050505] px-6">
        <div
          data-testid="register-success"
          className="max-w-md border border-[#39ff14]/40 bg-[#0a1a0a] p-8 text-center"
        >
          <CheckCircle2 className="mx-auto h-10 w-10 text-[#39ff14]" />
          <h2 className="mt-4 text-xl font-semibold text-neutral-100">
            Request submitted
          </h2>
          <p className="mt-2 mono text-[12px] text-neutral-400">
            Your account is <span className="text-[#ffb800]">pending</span>{" "}
            admin approval. You&#39;ll be able to sign in once an admin approves it.
          </p>
          <button
            data-testid="back-to-login"
            onClick={() => nav("/login")}
            className="mt-6 border border-[#39ff14] px-6 py-2 mono text-xs uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14] hover:text-black"
          >
            Back to login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen items-center justify-center bg-[#050505] px-6">
      <form
        onSubmit={submit}
        data-testid="register-form"
        className="w-full max-w-sm"
      >
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center border border-[#00f0ff] text-[#00f0ff]">
            <Radio className="h-4 w-4" />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.4em] text-neutral-500">
              Request Access
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-neutral-100">
              New operator account
            </h1>
          </div>
        </div>

        <p className="mb-4 mono text-[11px] text-neutral-500">
          Accounts are created in <span className="text-[#ffb800]">pending</span>{" "}
          state. An administrator must approve them before you can sign in.
        </p>

        <Field label="Email">
          <input
            data-testid="register-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full border border-[#2a2a2a] bg-black px-3 py-2 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
          />
        </Field>

        <Field label="Callsign (optional)">
          <input
            data-testid="register-callsign"
            value={callsign}
            onChange={(e) => setCallsign(e.target.value)}
            maxLength={16}
            className="w-full border border-[#2a2a2a] bg-black px-3 py-2 mono text-sm uppercase tracking-wide text-neutral-100 outline-none focus:border-[#00f0ff]"
          />
        </Field>

        <Field label="Password (min 6)">
          <input
            data-testid="register-password"
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full border border-[#2a2a2a] bg-black px-3 py-2 mono text-sm text-neutral-100 outline-none focus:border-[#00f0ff]"
          />
        </Field>

        {err && (
          <div
            data-testid="register-error"
            className="mb-3 border border-[#ff3b30]/60 bg-[#1a0505] px-3 py-2 mono text-[11px] text-[#ff3b30]"
          >
            {err}
          </div>
        )}

        <button
          data-testid="register-submit"
          type="submit"
          disabled={loading}
          className="w-full border border-[#00f0ff] bg-[#001a1f] px-4 py-2 mono text-xs uppercase tracking-[0.25em] text-[#00f0ff] transition-colors hover:bg-[#00f0ff] hover:text-black disabled:opacity-50"
        >
          {loading ? "submitting…" : "Request Access →"}
        </button>

        <div className="mt-6 mono text-[11px] text-neutral-500">
          Already have an account?{" "}
          <Link to="/login" className="text-[#00f0ff] hover:underline" data-testid="to-login">
            Sign in
          </Link>
        </div>
      </form>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="mb-3 block">
      <span className="mono mb-1 block text-[10px] uppercase tracking-widest text-neutral-500">
        {label}
      </span>
      {children}
    </label>
  );
}
