// Thin typed client over the FastAPI backend.
// Base URL: VITE_API_BASE if set, else "/api" (Vite dev proxy -> :8080).

// Default to same-origin ("") — the app is served by the same FastAPI server in
// prod and local single-container. Only set VITE_API_BASE for the separate Vite
// dev server (e.g. "/api"). Never pass "/" via Git Bash — it gets path-mangled.
const _rawBase = import.meta.env.VITE_API_BASE as string | undefined;
const BASE = _rawBase == null ? "" : _rawBase.replace(/\/$/, "");

// Reads the current token straight from storage so requests never race the
// auth provider's effects (important right after the OAuth full-page reload).
let tokenGetter: () => string | null = () => {
  try {
    return JSON.parse(localStorage.getItem("taxassist.auth") || "{}").token || null;
  } catch {
    return null;
  }
};
export function setTokenGetter(fn: () => string | null) {
  tokenGetter = fn;
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = tokenGetter();
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// ── types ────────────────────────────────────────────────────────────────────
export interface Profile {
  id: string;
  display_name: string;
  relation: string;
  itr_type: string;
  drive_folder_id: string;
  sheets_id?: string;
}
export interface Me {
  user: { user_id: string; email: string };
  profiles: Profile[];
}
export interface TaskItem {
  key: string;
  label: string;
  description?: string | null;
  status: string;
  ui_status: "done" | "in_review" | "pending" | "skipped";
  kind: string;
}
export interface TaskGroup {
  title: string;
  items: TaskItem[];
}
export interface TasksResponse {
  profile_id: string;
  itr_type: string;
  stage: string;
  assessment_year?: string;
  next_action: string;
  next_step_detail: Record<string, any>;
  notification: { type?: string; reason_code?: string | null; context_metadata?: any };
  groups: TaskGroup[];
}
export interface AgentRun {
  id: string;
  status: "queued" | "running" | "waiting_reply" | "done" | "failed";
  detail: string;
  checkpoint?: Record<string, any> | null;
  created_at?: string | null;
  updated_at?: string | null;
}
export interface ItrSummary {
  filing_status?: string;
  tax_summary?: Record<string, any>;
  [k: string]: any;
}

// ── endpoints ────────────────────────────────────────────────────────────────
export const api = {
  me: () => req<Me>("/me"),
  demoLogin: () => req<{ token: string; email: string }>("/auth/demo", { method: "POST" }),
  listProfiles: () => req<Profile[]>("/profiles"),
  createProfile: (body: { display_name: string; relation: string; itr_type: string; drive_folder_id?: string }) =>
    req<{ id: string }>("/profiles", { method: "POST", body: JSON.stringify(body) }),
  tasks: (pid: string) => req<TasksResponse>(`/profiles/${pid}/tasks`),
  runs: (pid: string) => req<AgentRun[]>(`/profiles/${pid}/runs`),
  itr: (pid: string) => req<ItrSummary>(`/profiles/${pid}/itr`),
  seedDemo: (pid: string) => req<{ status: string }>(`/profiles/${pid}/seed-demo`, { method: "POST" }),
  run: (pid: string) =>
    req<{ status: string; tax_result?: Record<string, any>; summary?: string; run_id?: string; sheet_url?: string }>(
      `/profiles/${pid}/run`, { method: "POST" }),
  checkReply: (pid: string) =>
    req<{ status: "none" | "waiting" | "declined" | "completed"; summary?: string; reply?: string; sheet_url?: string }>(
      `/profiles/${pid}/check-reply`, { method: "POST" }),
  feedback: (body: { profile_id: string; kind: string; rating?: number; message?: string }) =>
    req<{ status: string; id: string }>("/feedback", { method: "POST", body: JSON.stringify(body) }),

  // Streams the portal-ready ITR JSON (auth header required, so we fetch+blob
  // rather than a bare <a href>) and triggers a browser download.
  downloadItrJson: async (pid: string, fallbackName: string) => {
    const token = tokenGetter();
    const res = await fetch(`${BASE}/profiles/${pid}/itr-json`, {
      cache: "no-store",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail ?? detail; } catch { /* ignore */ }
      throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    const cd = res.headers.get("content-disposition") || "";
    const m = cd.match(/filename="?([^"]+)"?/);
    const filename = m?.[1] || fallbackName;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
