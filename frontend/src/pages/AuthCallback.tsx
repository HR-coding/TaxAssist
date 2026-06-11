import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { useAuth } from "../lib/auth";
import { Spinner } from "../components/ui";

/** Lands here after Google redirects back: /auth/callback#token=... (or #error=...). */
export default function AuthCallback() {
  const { loginWithToken } = useAuth();
  const nav = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const token = hash.get("token");
    const err = hash.get("error");
    if (token) {
      loginWithToken(token);
      window.location.replace("/app");
    } else {
      setError(err || "Sign-in failed");
    }
  }, []);

  return (
    <div className="container-x grid min-h-[70vh] place-items-center py-16">
      <div className="card w-full max-w-md p-8 text-center">
        <div className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-accent-600 text-white">
          <ShieldCheck className="h-6 w-6" />
        </div>
        {error ? (
          <>
            <h1 className="mt-5 font-display text-xl font-bold text-ink-900">Sign-in failed</h1>
            <p className="mt-2 text-sm text-red-600">{error}</p>
            <Link to="/login" className="btn-primary mx-auto mt-6">Try again</Link>
          </>
        ) : (
          <>
            <h1 className="mt-5 font-display text-xl font-bold text-ink-900">Signing you in…</h1>
            <p className="mt-2 flex items-center justify-center gap-2 text-sm text-ink-400">
              <Spinner /> Finalizing your Google session
            </p>
          </>
        )}
      </div>
    </div>
  );
}
