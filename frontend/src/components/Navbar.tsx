import { Link, useLocation, useNavigate } from "react-router-dom";
import { ShieldCheck, LogOut } from "lucide-react";
import { useAuth } from "../lib/auth";

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent-600 text-white">
        <ShieldCheck className="h-5 w-5" />
      </span>
      <span className="font-display text-lg font-bold tracking-tight text-ink-900">TaxAssist</span>
    </Link>
  );
}

export default function Navbar() {
  const { email, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const onLanding = loc.pathname === "/";

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-paper/85 backdrop-blur-md">
      <div className="container-x flex h-16 items-center justify-between">
        <Logo />
        <nav className="flex items-center gap-1">
          {onLanding && (
            <>
              <a href="#how" className="hidden rounded-lg px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900 sm:block">How it works</a>
              <a href="#trust" className="hidden rounded-lg px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900 sm:block">Transparency</a>
              <a href="#security" className="hidden rounded-lg px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900 sm:block">Security</a>
            </>
          )}
          {email ? (
            <>
              <Link to="/app" className="btn-secondary ml-1">Dashboard</Link>
              <button onClick={() => { logout(); nav("/"); }} className="btn-secondary" title="Sign out" aria-label="Sign out">
                <LogOut className="h-4 w-4" />
              </button>
            </>
          ) : (
            <Link to="/login" className="btn-primary ml-1">Sign in</Link>
          )}
        </nav>
      </div>
    </header>
  );
}
