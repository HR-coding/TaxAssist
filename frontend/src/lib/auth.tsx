// Auth context. Two modes:
//  • Dev mode (default): a lightweight email login -> bearer "dev:<email>", which the
//    backend accepts when FIREBASE_PROJECT_ID is unset. Lets the app run end-to-end now.
//  • Firebase mode (production): drop your Firebase ID token in via setToken(); the
//    backend verifies it. The UI seam below is identical, so swapping is trivial.
import { createContext, useContext, useEffect, useMemo, useState, ReactNode } from "react";
import { setTokenGetter } from "./api";

interface AuthState {
  email: string | null;
  token: string | null;
  login: (email: string) => void;
  loginWithToken: (token: string) => void;
  logout: () => void;
}

const Ctx = createContext<AuthState | null>(null);
const KEY = "taxassist.auth";

function decodeJwtEmail(token: string): string {
  try {
    return JSON.parse(atob(token.split(".")[1])).email || "account";
  } catch {
    return "account";
  }
}

function readStored(): { email?: string; token?: string } {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "{}");
  } catch {
    return {};
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  // Initialize synchronously from storage so protected routes see auth on first render.
  const [email, setEmail] = useState<string | null>(() => readStored().email ?? null);
  const [token, setToken] = useState<string | null>(() => readStored().token ?? null);

  // Keep the api client's token in sync.
  useEffect(() => {
    setTokenGetter(() => token);
  }, [token]);

  const value = useMemo<AuthState>(
    () => ({
      email,
      token,
      login: (e: string) => {
        const t = `dev:${e.trim().toLowerCase()}`;
        setEmail(e);
        setToken(t);
        localStorage.setItem(KEY, JSON.stringify({ email: e, token: t }));
      },
      loginWithToken: (t: string) => {
        const e = decodeJwtEmail(t);
        setEmail(e);
        setToken(t);
        localStorage.setItem(KEY, JSON.stringify({ email: e, token: t }));
      },
      logout: () => {
        setEmail(null);
        setToken(null);
        localStorage.removeItem(KEY);
      },
    }),
    [email, token]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside provider");
  return v;
}
