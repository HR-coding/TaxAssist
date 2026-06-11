import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft, RefreshCw, Eye, Activity, ListChecks, Mail, Bot, Sparkles,
  ThumbsUp, ThumbsDown, ChevronRight, Gauge, FolderOpen, Table2, ExternalLink,
  FileSpreadsheet, Check, Download,
} from "lucide-react";
import { api, AgentRun, ItrSummary, Profile as ProfileT, TasksResponse } from "../lib/api";
import { useAuth } from "../lib/auth";
import { PageLoader, RunBadge, Spinner, StatusBadge, timeAgo } from "../components/ui";

const STAGES = ["PREREQUISITES", "VALIDATING_INCOME", "VALIDATING_DEDUCTIONS", "COMPUTATION", "DONE"];
const STAGE_LABEL: Record<string, string> = {
  PREREQUISITES: "Prerequisites", VALIDATING_INCOME: "Income", VALIDATING_DEDUCTIONS: "Deductions",
  COMPUTATION: "Computation", DONE: "Done",
};

export default function Profile() {
  const { pid = "" } = useParams();
  const [profile, setProfile] = useState<ProfileT | null>(null);
  const [tasks, setTasks] = useState<TasksResponse | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [itr, setItr] = useState<ItrSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [awaitingReply, setAwaitingReply] = useState(false);
  const [checking, setChecking] = useState(false);
  const [runResult, setRunResult] = useState<{ kind: "ok" | "declined" | "error"; text: string; sheetUrl?: string } | null>(null);
  const [err, setErr] = useState("");
  const pollRef = useRef<number | null>(null);
  const replyRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    setErr("");
    try {
      const [t, r, i, all] = await Promise.all([api.tasks(pid), api.runs(pid), api.itr(pid), api.listProfiles()]);
      setTasks(t); setRuns(r); setItr(i);
      setProfile(all.find((p) => p.id === pid) ?? null);
      // Resume the waiting state after a page refresh: if the latest run is parked
      // on a real email gate, keep watching the inbox.
      const waiting = r.find((x) => x.status === "waiting_reply" && x.checkpoint?.thread_id);
      if (waiting) startReplyWatch();
    } catch (e: any) {
      setErr(e.message || "Failed to load workspace");
    } finally {
      setLoading(false);
    }
  }, [pid]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => () => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    if (replyRef.current) window.clearInterval(replyRef.current);
  }, []);

  function startReplyWatch() {
    setAwaitingReply(true);
    if (replyRef.current) return; // already watching
    replyRef.current = window.setInterval(() => { checkReplyNow(false); }, 15000);
  }
  function stopReplyWatch() {
    setAwaitingReply(false);
    if (replyRef.current) { window.clearInterval(replyRef.current); replyRef.current = null; }
  }

  async function checkReplyNow(manual: boolean) {
    if (manual) setChecking(true);
    try {
      const r = await api.checkReply(pid);
      if (r.status === "completed") {
        stopReplyWatch();
        setRunResult({ kind: "ok", text: r.summary || "return computed", sheetUrl: r.sheet_url });
        await load();
      } else if (r.status === "declined") {
        stopReplyWatch();
        setRunResult({ kind: "declined", text: `you declined by email ("${r.reply ?? ""}")` });
        await load();
      } else if (r.status === "none") {
        stopReplyWatch();
      }
      // "waiting": keep watching silently
    } catch { /* transient — keep watching */ } finally {
      if (manual) setChecking(false);
    }
  }

  async function seed() {
    setBusy(true);
    try { await api.seedDemo(pid); await load(); } finally { setBusy(false); }
  }

  async function runAgent() {
    setRunning(true); setRunResult(null);
    // Poll the run log while the agent works, so each step appears live.
    pollRef.current = window.setInterval(async () => {
      try { setRuns(await api.runs(pid)); } catch { /* keep polling */ }
    }, 1200);
    try {
      const r = await api.run(pid);
      if (r.status === "waiting_reply") {
        startReplyWatch();
      } else {
        setRunResult({ kind: "ok", text: r.summary || "Filing run complete", sheetUrl: r.sheet_url });
      }
    } catch (e: any) {
      setRunResult({ kind: "error", text: e.message || "error" });
    } finally {
      if (pollRef.current) { window.clearInterval(pollRef.current); pollRef.current = null; }
      setRunning(false);
      await load();
    }
  }

  if (loading) return <div className="container-x"><PageLoader label="Loading workspace" /></div>;

  if (err) return (
    <div className="container-x py-12">
      <BackLink />
      <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{err}</div>
    </div>
  );

  const stageIdx = Math.max(0, STAGES.indexOf(tasks?.stage || "PREREQUISITES"));
  const allItems = tasks?.groups.flatMap((g) => g.items) ?? [];
  const done = allItems.filter((i) => i.ui_status === "done").length;
  const total = allItems.filter((i) => i.ui_status !== "skipped").length || 1;
  const pct = Math.round((done / total) * 100);

  return (
    <div className="container-x py-10">
      <BackLink />

      {/* header */}
      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-extrabold tracking-tight text-ink-900">
            {profile?.display_name ?? "Filing workspace"}
          </h1>
          <p className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-ink-500">
            <span className="chip border-line bg-page text-ink-600">{tasks?.itr_type}</span>
            <span>AY {tasks?.assessment_year}</span>
            <span className="text-ink-400">·</span>
            <span>{done}/{total} tasks verified</span>
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={load}><RefreshCw className="h-4 w-4" /> Refresh</button>
          <button className="btn-secondary" onClick={seed} disabled={busy}>
            {busy ? <Spinner /> : <Sparkles className="h-4 w-4" />} Demo data
          </button>
          <button className="btn-primary" onClick={runAgent} disabled={running || awaitingReply}
            title={awaitingReply ? "Waiting for your email reply" : undefined}>
            {running ? <Spinner /> : <Bot className="h-4 w-4" />} {running ? "Agent working…" : "Run filing agent"}
          </button>
        </div>
      </div>

      {running && (
        <div className="mt-4 flex items-center gap-3 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
          <Spinner className="text-blue-600" />
          <span>The agent is working — each step appears in the activity feed on the right as it happens.</span>
        </div>
      )}
      {awaitingReply && !running && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <span className="flex items-center gap-3">
            <Mail className="h-5 w-5 shrink-0 text-amber-600" />
            <span>
              <span className="font-semibold">The agent emailed you the extracted figures.</span>{" "}
              Reply <span className="font-semibold">CONFIRM</span> in Gmail to approve — we check your inbox every 15 seconds.
            </span>
          </span>
          <button className="btn-secondary" onClick={() => checkReplyNow(true)} disabled={checking}>
            {checking ? <Spinner /> : <RefreshCw className="h-4 w-4" />} I replied — check now
          </button>
        </div>
      )}
      {runResult && !running && (
        runResult.kind === "ok" ? (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-accent-200 bg-accent-50 p-4 text-sm text-accent-900">
            <span className="flex items-center gap-3">
              <Check className="h-5 w-5 shrink-0 text-accent-600" />
              <span><span className="font-semibold">Filing run complete</span> — {runResult.text}. Tasks, activity, and the computed return have updated.</span>
            </span>
            {runResult.sheetUrl && (
              <a href={runResult.sheetUrl} target="_blank" rel="noreferrer" className="btn-secondary">
                <Table2 className="h-4 w-4" /> Open results sheet
              </a>
            )}
          </div>
        ) : (
          <div className="mt-4 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <Mail className="h-5 w-5 shrink-0" />
            <span><span className="font-semibold">Run stopped</span> — {runResult.text}.</span>
          </div>
        )
      )}

      {/* stage stepper + progress */}
      <div className="card mt-6 p-6">
        <div className="flex items-center justify-between">
          <p className="label">Filing stage</p>
          <span className="text-sm font-semibold text-accent-700">{pct}% complete</span>
        </div>
        <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-page">
          <div className="h-full rounded-full bg-accent-600 transition-all" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-2">
          {STAGES.map((s, i) => (
            <span key={s} className="flex items-center gap-2">
              <span className={`chip ${i < stageIdx ? "border-accent-200 bg-accent-50 text-accent-900"
                : i === stageIdx ? "border-accent-600 bg-accent-600 text-white"
                : "border-line bg-paper text-ink-400"}`}>
                {i < stageIdx && <Check className="h-3 w-3" />} {STAGE_LABEL[s]}
              </span>
              {i < STAGES.length - 1 && <ChevronRight className="h-3.5 w-3.5 text-ink-400/60" />}
            </span>
          ))}
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        {/* LEFT: tasks */}
        <div className="space-y-6 lg:col-span-2">
          <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-ink-900">
            <ListChecks className="h-5 w-5 text-accent-600" /> All tasks
          </h2>
          {tasks?.groups.map((g) => (
            <div key={g.title} className="card p-6">
              <h3 className="font-display text-base font-semibold text-ink-900">{g.title}</h3>
              <div className="mt-3 divide-y divide-line">
                {g.items.length === 0 && <p className="py-3 text-sm text-ink-400">No items.</p>}
                {g.items.map((it) => (
                  <div key={it.key} className="flex items-start justify-between gap-4 py-3.5">
                    <div>
                      <p className="text-sm font-medium text-ink-900">{it.label}</p>
                      {it.description && <p className="mt-0.5 text-xs text-ink-400">{it.description}</p>}
                    </div>
                    <StatusBadge status={it.ui_status} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* RIGHT: side panel */}
        <div className="space-y-6">
          <QuickAccess profile={profile} />
          {tasks && <TransparencyPanel tasks={tasks} />}
          <ActivityTimeline runs={runs} running={running} onSeed={seed} busy={busy} />
          {itr && itr.filing_status && itr.filing_status !== "NOT_STARTED" && (
            <ItrCard itr={itr} pid={pid} profile={profile} />
          )}
          <FeedbackCard pid={pid} />
        </div>
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/app" className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-500 hover:text-ink-900">
      <ArrowLeft className="h-4 w-4" /> All profiles
    </Link>
  );
}

function QuickAccess({ profile }: { profile: ProfileT | null }) {
  // Pin links to the account the user signed in with — otherwise Google opens
  // them in the browser's default account.
  const { email } = useAuth();
  const au = email ? `?authuser=${encodeURIComponent(email)}` : "";
  const driveUrl = profile?.drive_folder_id
    ? `https://drive.google.com/drive/folders/${profile.drive_folder_id}${au}`
    : `https://drive.google.com/drive/my-drive${au}`;
  const sheetsUrl = profile?.sheets_id
    ? `https://docs.google.com/spreadsheets/d/${profile.sheets_id}/edit${au}`
    : `https://docs.google.com/spreadsheets/${au}`;
  return (
    <div className="card p-5">
      <h3 className="font-display text-base font-semibold text-ink-900">Quick access</h3>
      <p className="mt-1 text-xs text-ink-400">Where the agent reads and writes for this profile.</p>
      <div className="mt-4 space-y-2.5">
        <a href={driveUrl} target="_blank" rel="noreferrer"
          className="group flex items-center justify-between rounded-xl border border-line px-4 py-3 transition-colors hover:border-accent-200 hover:bg-accent-50/40">
          <span className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-amber-50 text-amber-600"><FolderOpen className="h-5 w-5" /></span>
            <span>
              <span className="block text-sm font-medium text-ink-900">Drive folder</span>
              <span className="block text-xs text-ink-400">{profile?.drive_folder_id ? "Your tax documents" : "Not linked — opens My Drive"}</span>
            </span>
          </span>
          <ExternalLink className="h-4 w-4 text-ink-400 group-hover:text-accent-700" />
        </a>
        <a href={sheetsUrl} target="_blank" rel="noreferrer"
          className="group flex items-center justify-between rounded-xl border border-line px-4 py-3 transition-colors hover:border-accent-200 hover:bg-accent-50/40">
          <span className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent-50 text-accent-700"><Table2 className="h-5 w-5" /></span>
            <span>
              <span className="block text-sm font-medium text-ink-900">Results sheet</span>
              <span className="block text-xs text-ink-400">{profile?.sheets_id ? "Findings & computed return" : "Not linked — opens Sheets"}</span>
            </span>
          </span>
          <ExternalLink className="h-4 w-4 text-ink-400 group-hover:text-accent-700" />
        </a>
      </div>
    </div>
  );
}

function TransparencyPanel({ tasks }: { tasks: TasksResponse }) {
  const n = tasks.notification || {};
  const NOTI: Record<string, string> = {
    REQUEST: "Requesting information from you",
    VERIFY: "Verifying an uploaded document",
    ALERT: "Flagged a variance to review",
    ERROR: "Blocked an unsafe action",
    NONE: "Idle — nothing pending",
  };
  return (
    <div className="card p-5">
      <div className="flex items-center gap-2">
        <Eye className="h-5 w-5 text-accent-600" />
        <h3 className="font-display text-base font-semibold text-ink-900">What the agent is doing</h3>
      </div>
      <div className="mt-4 space-y-3.5">
        <Row icon={<Bot className="h-4 w-4 text-accent-600" />} label="Current state" value={NOTI[n.type || "NONE"] ?? n.type} />
        <Row icon={<Gauge className="h-4 w-4 text-accent-600" />} label="Next deterministic step"
          value={<code className="rounded bg-accent-50 px-1.5 py-0.5 text-xs font-medium text-accent-700">{tasks.next_action}</code>} />
        {n.reason_code && <Row icon={<Activity className="h-4 w-4 text-amber-500" />} label="Reason" value={n.reason_code} />}
        {n.context_metadata?.target_schedule && (
          <Row icon={<ChevronRight className="h-4 w-4 text-ink-400" />} label="Target"
            value={<span className="text-ink-600">{n.context_metadata.target_schedule}</span>} />
        )}
      </div>
      <p className="mt-4 rounded-lg bg-page p-3 text-xs leading-relaxed text-ink-500">
        The next step is chosen by a <span className="font-semibold text-ink-700">deterministic state machine</span>,
        not the AI — the workflow can't be steered off-course by the model.
      </p>
    </div>
  );
}

function Row({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5">{icon}</span>
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">{label}</p>
        <p className="text-sm text-ink-700">{value}</p>
      </div>
    </div>
  );
}

function ActivityTimeline({ runs, running, onSeed, busy }: { runs: AgentRun[]; running: boolean; onSeed: () => void; busy: boolean }) {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-accent-600" />
          <h3 className="font-display text-base font-semibold text-ink-900">Agent activity</h3>
        </div>
        {running && <span className="chip border-blue-200 bg-blue-50 text-blue-700"><Spinner className="h-3 w-3" /> live</span>}
      </div>
      {runs.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-line p-5 text-center">
          <p className="text-sm text-ink-400">No runs yet. Start the agent, or load demo data.</p>
          <button className="btn-secondary mt-3" onClick={onSeed} disabled={busy}>
            {busy ? <Spinner /> : <Sparkles className="h-4 w-4" />} Simulate a run
          </button>
        </div>
      ) : (
        <ol className="mt-4">
          {runs.map((r, i) => (
            <li key={r.id} className="relative pb-5 pl-6 last:pb-0">
              {i < runs.length - 1 && <span className="absolute left-[5px] top-4 h-full w-px bg-line" />}
              <span className={`absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full ${r.status === "failed" ? "bg-red-400" : r.status === "waiting_reply" ? "bg-amber-400" : "bg-accent-500"}`} />
              <div className="flex items-center justify-between gap-2">
                <RunBadge status={r.status} />
                <span className="text-xs text-ink-400">{timeAgo(r.updated_at || r.created_at)}</span>
              </div>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{r.detail}</p>
              {r.checkpoint?.sheet_url && (
                <a href={r.checkpoint.sheet_url} target="_blank" rel="noreferrer"
                  className="mt-1 inline-flex items-center gap-1.5 text-xs font-medium text-accent-700 hover:underline">
                  <Table2 className="h-3.5 w-3.5" /> Open the results sheet
                </a>
              )}
              {r.status === "waiting_reply" && r.checkpoint?.thread_id && (
                <p className="mt-1 inline-flex items-center gap-1.5 text-xs font-medium text-amber-600">
                  <Mail className="h-3.5 w-3.5" /> Reply CONFIRM to the email to resume this run
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function ItrCard({ itr, pid, profile }: { itr: ItrSummary; pid: string; profile: ProfileT | null }) {
  const summary = itr.tax_summary || {};
  const fmt = (v: any) => typeof v === "number" ? `₹${v.toLocaleString("en-IN")}` : String(v);
  const KEYS = ["taxable_income", "tax_liability", "taxes_paid", "net_tax_payable", "refund_due"];
  const rows = KEYS.filter((k) => k in summary);

  const [downloading, setDownloading] = useState(false);
  const [dlErr, setDlErr] = useState("");
  async function download() {
    setDownloading(true); setDlErr("");
    const name = `${profile?.itr_type ?? "ITR"}_${(profile?.display_name ?? "taxpayer").replace(/\s+/g, "_")}_AY2026-27.json`;
    try {
      await api.downloadItrJson(pid, name);
    } catch (e: any) {
      setDlErr(e.message || "Download failed");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2">
        <FileSpreadsheet className="h-5 w-5 text-accent-600" />
        <h3 className="font-display text-base font-semibold text-ink-900">Computed return</h3>
      </div>
      <p className="mt-1 text-xs text-ink-400">Deterministic — official slabs, no AI in the math.</p>
      <div className="mt-3 divide-y divide-line">
        {(rows.length ? rows : Object.keys(summary).slice(0, 6)).map((k) => (
          <div key={k} className="flex items-center justify-between py-2 text-sm">
            <span className="capitalize text-ink-500">{k.replace(/_/g, " ")}</span>
            <span className={`font-semibold ${k === "refund_due" && summary[k] > 0 ? "text-accent-700" : "text-ink-900"}`}>{fmt(summary[k])}</span>
          </div>
        ))}
      </div>
      {"cheaper_regime" in summary && (
        <p className="mt-3 rounded-lg bg-accent-50 px-3 py-2 text-xs text-accent-900">
          Cheaper regime for you: <span className="font-semibold">{String(summary.cheaper_regime)}</span>
          {"old_regime_payable" in summary && <> · old regime would cost ₹{Number(summary.old_regime_payable).toLocaleString("en-IN")} more</>}
        </p>
      )}
      <button className="btn-secondary mt-4 w-full justify-center" onClick={download} disabled={downloading}>
        {downloading ? <Spinner /> : <Download className="h-4 w-4" />} Download ITR JSON
      </button>
      <p className="mt-2 text-center text-[11px] leading-relaxed text-ink-400">
        Official offline-utility format — import it at the income-tax portal to e-file.
      </p>
      {dlErr && <p className="mt-2 text-center text-xs text-red-600">{dlErr}</p>}
    </div>
  );
}

function FeedbackCard({ pid }: { pid: string }) {
  const [sent, setSent] = useState<null | "up" | "down">(null);
  const [busy, setBusy] = useState(false);
  async function send(kind: "up" | "down") {
    setBusy(true);
    try {
      await api.feedback({ profile_id: pid, kind: "thumbs", rating: kind === "up" ? 1 : 0 });
      setSent(kind);
    } finally { setBusy(false); }
  }
  return (
    <div className="card p-5">
      <h3 className="font-display text-base font-semibold text-ink-900">How is this going?</h3>
      <p className="mt-1 text-xs text-ink-400">Feedback is pseudonymous and PII-scrubbed.</p>
      {sent ? (
        <p className="mt-3 text-sm font-medium text-accent-700">Thanks — noted.</p>
      ) : (
        <div className="mt-3 flex gap-2">
          <button className="btn-secondary" disabled={busy} onClick={() => send("up")}><ThumbsUp className="h-4 w-4" /> Good</button>
          <button className="btn-secondary" disabled={busy} onClick={() => send("down")}><ThumbsDown className="h-4 w-4" /> Needs work</button>
        </div>
      )}
    </div>
  );
}
