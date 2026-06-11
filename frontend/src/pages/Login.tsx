import { FormEvent, useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { ShieldCheck, ArrowRight, Mail } from "lucide-react";
import { useAuth } from "../lib/auth";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = useState("");
  const [err, setErr] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    const v = email.trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) {
      setErr("Enter a valid email address.");
      return;
    }
    login(v);
    nav(loc.state?.from || "/app", { replace: true });
  }

  return (
    <div className="container-x grid min-h-[72vh] place-items-center py-16">
      <div className="card w-full max-w-md p-8">
        <div className="grid h-11 w-11 place-items-center rounded-xl bg-accent-600 text-white">
          <ShieldCheck className="h-6 w-6" />
        </div>
        <h1 className="mt-5 font-display text-2xl font-bold text-ink-900">Welcome to TaxAssist</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-500">
          Sign in with Google to authorize Drive, Gmail, Calendar &amp; Sheets — the agent then
          works on your own account.
        </p>

        <button
          onClick={() => { window.location.href = "/auth/google/login"; }}
          className="btn-secondary mt-6 w-full py-3"
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z"/><path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38z"/></svg>
          Continue with Google
        </button>

        <div className="my-5 flex items-center gap-3 text-xs text-ink-400">
          <span className="h-px flex-1 bg-line" /> or email <span className="h-px flex-1 bg-line" />
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="label">Email address</label>
            <div className="relative mt-1.5">
              <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
              <input
                className="input pl-9"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => { setEmail(e.target.value); setErr(""); }}
              />
            </div>
            {err && <p className="mt-1.5 text-xs text-red-600">{err}</p>}
          </div>
          <button type="submit" className="btn-primary w-full py-3">
            Continue <ArrowRight className="h-4 w-4" />
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-ink-400">
          By continuing you agree to deterministic tax computation and DPDP/GDPR data handling.{" "}
          <Link to="/" className="text-accent-700 hover:underline">Back home</Link>
        </p>
      </div>
    </div>
  );
}
