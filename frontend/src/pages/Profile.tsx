import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft, RefreshCw, ListChecks, Mail, Bot, Sparkles,
  ThumbsUp, ThumbsDown, ChevronRight, FolderOpen, Table2, ExternalLink,
  FileSpreadsheet, Check, Download, HelpCircle, X, Play, AlertCircle, ShieldCheck,
} from "lucide-react";
import { api, AgentRun, ItrSummary, Profile as ProfileT, TasksResponse } from "../lib/api";
import { useAuth } from "../lib/auth";
import { PageLoader, RunBadge, Spinner, StatusBadge, timeAgo } from "../components/ui";

const STAGES = ["PREREQUISITES", "VALIDATING_INCOME", "VALIDATING_DEDUCTIONS", "COMPUTATION", "DONE"];
const STAGE_LABEL: Record<string, string> = {
  PREREQUISITES: "Prerequisites", VALIDATING_INCOME: "Income", VALIDATING_DEDUCTIONS: "Deductions",
  COMPUTATION: "Computation", DONE: "Done",
};

// ── plain-English translation (no codes / technical detail ever reach the UI) ──
function humanizeAction(code?: string): string {
  const c = (code || "").toUpperCase();
  if (!c) return "Reviewing your filing";
  if (c === "DONE") return "Everything's verified — your return is ready to download";
  if (c.includes("PAN") && c.includes("AADHAAR")) return "Checking that your PAN and Aadhaar are linked";
  if (c.includes("BANK")) return "Validating your bank account so a refund can be paid";
  if (c.includes("PERSONAL") || c.includes("PART_A")) return "Confirming your personal details";
  if (c.includes("PROCESS_UPLOAD")) return "Reading the figures from the document you uploaded";
  if (c.includes("AWAITING_INGESTION")) return "Waiting for you to upload a tax document";
  if (c.includes("RECONCILE") || c.includes("AIS") || c.includes("TIS"))
    return "Cross-checking your income against the tax department's records";
  if (c.includes("COMPUTE_TOTAL_INCOME")) return "Adding up your total income across all sources";
  if (c.includes("COMPUTE")) return "Calculating your tax from the official slab rates";
  if (c.includes("VERIFY")) return "Verifying your details";
  return "Working through your filing checklist";
}

const STATE_TEXT: Record<string, string> = {
  REQUEST: "Waiting on some information from you",
  VERIFY: "Reviewing a document you uploaded",
  ALERT: "Flagged something for you to check",
  ERROR: "Paused to keep your data safe",
  NONE: "Idle — nothing needs your attention right now",
};

function friendlyError(msg?: string): string {
  const m = (msg || "").toLowerCase();
  if (m.includes("sheet")) return "Couldn't save the results to Google Sheets. Link a Drive folder, then run again.";
  if (m.includes("drive")) return "Couldn't reach your Google Drive. Reconnect access and try again.";
  if (m.includes("token") || m.includes("auth") || m.includes("credential") || m.includes("401"))
    return "Your Google access needs reconnecting. Sign in again to continue.";
  if (m.includes("email") || m.includes("gmail")) return "Couldn't send the confirmation email. Check Gmail access and retry.";
  return "Something went wrong during the run. Please try again.";
}

const fmtINR = (v: any) => (typeof v === "number" ? `₹${v.toLocaleString("en-IN")}` : String(v ?? "—"));

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
  const [helpOpen, setHelpOpen] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [dlErr, setDlErr] = useState("");
  const pollRef = useRef<number | null>(null);
  const replyRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    setErr("");
    try {
      const [t, r, i, all] = await Promise.all([api.tasks(pid), api.runs(pid), api.itr(pid), api.listProfiles()]);
      setTasks(t); setRuns(r); setItr(i);
      setProfile(all.find((p) => p.id === pid) ?? null);
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
    if (replyRef.current) return;
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
        setRunResult({ kind: "ok", text: "your figures were confirmed and the return computed", sheetUrl: r.sheet_url });
        await load();
      } else if (r.status === "declined") {
        stopReplyWatch();
        setRunResult({ kind: "declined", text: "you declined the figures by email, so the run was stopped" });
        await load();
      } else if (r.status === "none") {
        stopReplyWatch();
      }
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
    pollRef.current = window.setInterval(async () => {
      try { setRuns(await api.runs(pid)); } catch { /* keep polling */ }
    }, 1200);
    try {
      const r = await api.run(pid);
      if (r.status === "waiting_reply") {
        startReplyWatch();
      } else {
        setRunResult({ kind: "ok", text: "your return was computed from the official slab rates", sheetUrl: r.sheet_url });
      }
    } catch (e: any) {
      setRunResult({ kind: "error", text: friendlyError(e.message) });
    } finally {
      if (pollRef.current) { window.clearInterval(pollRef.current); pollRef.current = null; }
      setRunning(false);
      await load();
    }
  }

  async function exportJson() {
    setDownloading(true); setDlErr("");
    const name = `${profile?.itr_type ?? "ITR"}_${(profile?.display_name ?? "taxpayer").replace(/\s+/g, "_")}.json`;
    try {
      await api.downloadItrJson(pid, name);
    } catch (e: any) {
      setDlErr(e.status === 404 ? "Run the agent first to compute your return." : friendlyError(e.message));
    } finally {
      setDownloading(false);
    }
  }

  if (loading) return <div className="container-x"><PageLoader label="Loading workspace" /></div>;

  if (err) return (
    <div className="container-x py-12">
      <BackLink />
      <div className="mt-6 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <p className="font-semibold">We couldn't load this workspace.</p>
          <p className="mt-0.5">Please refresh the page. If it keeps happening, sign in again.</p>
          <button className="btn-secondary mt-3" onClick={() => { setLoading(true); load(); }}>
            <RefreshCw className="h-4 w-4" /> Try again
          </button>
        </div>
      </div>
    </div>
  );

  const stageIdx = Math.max(0, STAGES.indexOf(tasks?.stage || "PREREQUISITES"));
  const allItems = tasks?.groups.flatMap((g) => g.items) ?? [];
  const done = allItems.filter((i) => i.ui_status === "done").length;
  const total = allItems.filter((i) => i.ui_status !== "skipped").length || 1;
  const pct = Math.round((done / total) * 100);
  const allStepsDone = allItems.length > 0 && done === total;

  return (
    <div className="container-x py-8">
      <BackLink />

      {/* ── toolbar ───────────────────────────────────────────────── */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-extrabold tracking-tight text-ink-900 sm:text-3xl">
            {profile?.display_name ?? "Filing workspace"}
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-500">
            <span className="chip border-line bg-page text-ink-600">{tasks?.itr_type}</span>
            <span>AY {tasks?.assessment_year}</span>
            <span className="text-ink-400">·</span>
            <span>{done}/{total} tasks verified</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-secondary" onClick={load} title="Refresh"><RefreshCw className="h-4 w-4" /> Refresh</button>
          <button className="btn-secondary" onClick={seed} disabled={busy} title="Load realistic demo data">
            {busy ? <Spinner /> : <Sparkles className="h-4 w-4" />} Demo data
          </button>
          <button
            className="btn-secondary"
            onClick={exportJson}
            disabled={!allStepsDone || downloading}
            title={allStepsDone ? "Download the portal-ready ITR JSON" : "Available once every task is verified"}
          >
            {downloading ? <Spinner /> : <Download className="h-4 w-4" />} Export ITR JSON
          </button>
          <button className="btn-primary" onClick={runAgent} disabled={running || awaitingReply}
            title={awaitingReply ? "Waiting for your email reply" : undefined}>
            {running ? <Spinner /> : <Play className="h-4 w-4" />} {running ? "Agent working…" : "Run filing agent"}
          </button>
          <button
            onClick={() => setHelpOpen(true)}
            className="grid h-9 w-9 place-items-center rounded-full border border-line bg-paper text-ink-500 transition-colors hover:bg-page hover:text-ink-900"
            aria-label="How to use TaxAssist"
            title="How to use TaxAssist"
          >
            <HelpCircle className="h-5 w-5" />
          </button>
        </div>
      </div>
      {dlErr && <p className="mt-2 text-right text-xs text-red-600">{dlErr}</p>}
      {!allStepsDone && (
        <p className="mt-2 text-right text-xs text-ink-400">
          The ITR JSON unlocks once every task is verified.
        </p>
      )}

      {/* ── action / status banner (always plain English) ─────────── */}
      <StatusBanner
        running={running}
        awaitingReply={awaitingReply}
        checking={checking}
        onCheck={() => checkReplyNow(true)}
        runResult={runResult}
        notificationType={tasks?.notification?.type}
        nextAction={tasks?.next_action}
        allStepsDone={allStepsDone}
      />

      {/* ── stage stepper + progress ──────────────────────────────── */}
      <div className="card mt-5 p-5 sm:p-6">
        <div className="flex items-center justify-between">
          <p className="label">Filing stage</p>
          <span className="text-sm font-semibold text-accent-700">{pct}% complete</span>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-y-2">
          {STAGES.map((s, i) => (
            <span key={s} className="flex items-center gap-2">
              <span className={`chip ${i < stageIdx ? "border-accent-200 bg-accent-50 text-accent-900"
                : i === stageIdx ? "border-accent-600 bg-accent-600 text-white"
                : "border-line bg-paper text-ink-400"}`}>
                {i < stageIdx ? <Check className="h-3 w-3" /> : <span className="text-[10px] font-bold">{i + 1}</span>} {STAGE_LABEL[s]}
              </span>
              {i < STAGES.length - 1 && <ChevronRight className="h-3.5 w-3.5 text-ink-400/60" />}
            </span>
          ))}
        </div>
        <div className="mt-4 flex items-center gap-3">
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-page">
            <div className="h-full rounded-full bg-accent-600 transition-all" style={{ width: `${pct}%` }} />
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        {/* LEFT: tasks */}
        <div className="space-y-5 lg:col-span-2">
          <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-ink-900">
            <ListChecks className="h-5 w-5 text-accent-600" /> All tasks
          </h2>
          {tasks?.groups.map((g) => (
            <div key={g.title} className="card p-5 sm:p-6">
              <h3 className="font-display text-base font-semibold text-ink-900">{g.title}</h3>
              <div className="mt-2 divide-y divide-line">
                {g.items.length === 0 && <p className="py-3 text-sm text-ink-400">Nothing here yet.</p>}
                {g.items.map((it) => (
                  <div key={it.key} className="flex items-start justify-between gap-4 py-3">
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
        <div className="space-y-5">
          <AgentStatusCard
            notificationType={tasks?.notification?.type}
            nextAction={tasks?.next_action}
            running={running}
            runs={runs}
            onSeed={seed}
            busy={busy}
          />
          {itr && itr.filing_status && itr.filing_status !== "NOT_STARTED"
            ? <ReturnCard itr={itr} canExport={allStepsDone} onExport={exportJson} downloading={downloading} />
            : <ReturnEmpty />}
          <QuickAccess profile={profile} />
          <FeedbackCard pid={pid} />
        </div>
      </div>

      {helpOpen && <HelpModal onClose={() => setHelpOpen(false)} />}
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

// ── the single "user action & agent status" box — plain English only ──────────
function StatusBanner({ running, awaitingReply, checking, onCheck, runResult, notificationType, nextAction, allStepsDone }: {
  running: boolean; awaitingReply: boolean; checking: boolean; onCheck: () => void;
  runResult: { kind: "ok" | "declined" | "error"; text: string; sheetUrl?: string } | null;
  notificationType?: string; nextAction?: string; allStepsDone: boolean;
}) {
  if (running) {
    return (
      <Banner tone="info" icon={<Spinner className="text-blue-600" />}
        title="The agent is working"
        body="Each step appears in the activity feed on the right as it happens. This usually takes a few seconds." />
    );
  }
  if (awaitingReply) {
    return (
      <Banner tone="warn" icon={<Mail className="h-5 w-5 text-amber-600" />}
        title="The agent emailed you the figures to confirm"
        body="Open the email and reply CONFIRM to approve, or DENY to stop. We check your inbox every few seconds."
        action={<button className="btn-secondary" onClick={onCheck} disabled={checking}>
          {checking ? <Spinner /> : <RefreshCw className="h-4 w-4" />} I replied — check now
        </button>} />
    );
  }
  if (runResult?.kind === "ok") {
    return (
      <Banner tone="ok" icon={<Check className="h-5 w-5 text-accent-600" />}
        title="Filing run complete"
        body={`Done — ${runResult.text}. Your tasks, activity and computed return are up to date.`}
        action={runResult.sheetUrl
          ? <a href={runResult.sheetUrl} target="_blank" rel="noreferrer" className="btn-secondary"><Table2 className="h-4 w-4" /> Open results sheet</a>
          : undefined} />
    );
  }
  if (runResult?.kind === "declined") {
    return <Banner tone="warn" icon={<Mail className="h-5 w-5 text-amber-600" />} title="Run stopped" body={`You ${runResult.text}.`} />;
  }
  if (runResult?.kind === "error") {
    return <Banner tone="error" icon={<AlertCircle className="h-5 w-5 text-red-600" />} title="The run couldn't finish" body={runResult.text} />;
  }
  if (allStepsDone) {
    return (
      <Banner tone="ok" icon={<Check className="h-5 w-5 text-accent-600" />}
        title="Everything's verified"
        body="Your return is ready — use “Export ITR JSON” above to download the portal-ready file." />
    );
  }
  // idle / in-progress: surface the current state + what happens next, in plain English
  const state = STATE_TEXT[notificationType || "NONE"] ?? STATE_TEXT.NONE;
  return (
    <Banner tone="neutral" icon={<Bot className="h-5 w-5 text-accent-600" />}
      title={state}
      body={`Up next: ${humanizeAction(nextAction)}. Press “Run filing agent” to continue.`} />
  );
}

function Banner({ tone, icon, title, body, action }: {
  tone: "ok" | "warn" | "error" | "info" | "neutral"; icon: React.ReactNode;
  title: string; body: string; action?: React.ReactNode;
}) {
  const cls: Record<string, string> = {
    ok: "border-accent-200 bg-accent-50 text-accent-900",
    warn: "border-amber-200 bg-amber-50 text-amber-800",
    error: "border-red-200 bg-red-50 text-red-700",
    info: "border-blue-200 bg-blue-50 text-blue-800",
    neutral: "border-line bg-paper text-ink-700",
  };
  return (
    <div className={`mt-5 flex flex-wrap items-start justify-between gap-3 rounded-xl border p-4 ${cls[tone]}`}>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 shrink-0">{icon}</span>
        <div>
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-0.5 text-sm leading-relaxed opacity-90">{body}</p>
        </div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

function AgentStatusCard({ notificationType, nextAction, running, runs, onSeed, busy }: {
  notificationType?: string; nextAction?: string; running: boolean;
  runs: AgentRun[]; onSeed: () => void; busy: boolean;
}) {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-accent-600" />
          <h3 className="font-display text-base font-semibold text-ink-900">Agent status</h3>
        </div>
        {running && <span className="chip border-blue-200 bg-blue-50 text-blue-700"><Spinner className="h-3 w-3" /> live</span>}
      </div>

      <div className="mt-3 flex items-center gap-2 text-sm">
        <span className={`h-2 w-2 shrink-0 rounded-full ${running ? "bg-blue-500" : "bg-ink-400"}`} />
        <span className="font-medium text-ink-900">{STATE_TEXT[notificationType || "NONE"] ?? STATE_TEXT.NONE}</span>
      </div>
      <div className="mt-3 rounded-lg bg-page p-3 text-sm text-ink-600">
        <span className="text-ink-500">What happens next: </span>{humanizeAction(nextAction)}.
        <span className="mt-1 block text-xs text-ink-400">
          Each step is chosen by a fixed, rule-based checklist — never guessed by the AI.
        </span>
      </div>

      <p className="label mt-4">Recent activity</p>
      {runs.length === 0 ? (
        <div className="mt-2 rounded-xl border border-dashed border-line p-4 text-center">
          <p className="text-sm text-ink-400">No activity yet. Run the agent, or load demo data.</p>
          <button className="btn-secondary mt-3" onClick={onSeed} disabled={busy}>
            {busy ? <Spinner /> : <Sparkles className="h-4 w-4" />} Simulate a run
          </button>
        </div>
      ) : (
        <ol className="mt-2">
          {runs.map((r, i) => (
            <li key={r.id} className="relative pb-4 pl-5 last:pb-0">
              {i < runs.length - 1 && <span className="absolute left-[3px] top-3 h-full w-px bg-line" />}
              <span className={`absolute left-0 top-1.5 h-2 w-2 rounded-full ${r.status === "failed" ? "bg-red-400" : r.status === "waiting_reply" ? "bg-amber-400" : "bg-accent-500"}`} />
              <div className="flex items-center justify-between gap-2">
                <RunBadge status={r.status} />
                <span className="text-xs text-ink-400">{timeAgo(r.updated_at || r.created_at)}</span>
              </div>
              <p className="mt-1 text-sm leading-relaxed text-ink-600">{r.detail}</p>
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

function ReturnCard({ itr, canExport, onExport, downloading }: {
  itr: ItrSummary; canExport: boolean; onExport: () => void; downloading: boolean;
}) {
  const summary = itr.tax_summary || {};
  const METRICS = [
    { k: "taxable_income", label: "Taxable income" },
    { k: "tax_liability", label: "Tax liability" },
    { k: "taxes_paid", label: "Taxes paid" },
    { k: "refund_due", label: "Refund due", hi: true },
  ];
  return (
    <div className="card p-5">
      <div className="flex items-center gap-2">
        <FileSpreadsheet className="h-5 w-5 text-accent-600" />
        <h3 className="font-display text-base font-semibold text-ink-900">Computed return</h3>
      </div>
      <p className="mt-1 text-xs text-ink-400">Calculated from the official slab rates — no AI in the math.</p>
      <div className="mt-3 grid grid-cols-2 gap-2.5">
        {METRICS.map((m) => (
          <div key={m.k} className="rounded-lg bg-page px-3 py-2.5">
            <p className="text-[11px] text-ink-500">{m.label}</p>
            <p className={`mt-0.5 text-base font-semibold ${m.hi && Number(summary[m.k]) > 0 ? "text-accent-700" : "text-ink-900"}`}>
              {fmtINR(summary[m.k])}
            </p>
          </div>
        ))}
      </div>
      {"cheaper_regime" in summary && (
        <p className="mt-3 rounded-lg bg-accent-50 px-3 py-2 text-xs text-accent-900">
          Cheaper regime for you: <span className="font-semibold">{String(summary.cheaper_regime)}</span>
          {"old_regime_payable" in summary && <> · the other regime would cost ₹{Number(summary.old_regime_payable).toLocaleString("en-IN")} more</>}
        </p>
      )}
      <button className="btn-secondary mt-4 w-full justify-center" onClick={onExport} disabled={!canExport || downloading}
        title={canExport ? "Download the portal-ready ITR JSON" : "Available once every task is verified"}>
        {downloading ? <Spinner /> : <Download className="h-4 w-4" />} Download ITR JSON
      </button>
      <p className="mt-2 text-center text-[11px] leading-relaxed text-ink-400">
        {canExport
          ? "Official offline-utility format — import it at the income-tax portal to e-file."
          : "Unlocks once every task is verified."}
      </p>
    </div>
  );
}

function ReturnEmpty() {
  return (
    <div className="card p-5">
      <div className="flex items-center gap-2">
        <FileSpreadsheet className="h-5 w-5 text-ink-400" />
        <h3 className="font-display text-base font-semibold text-ink-900">Computed return</h3>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-ink-400">
        Nothing computed yet. Press “Run filing agent” and your taxable income, tax and refund
        will appear here — calculated from the official slab rates.
      </p>
    </div>
  );
}

function QuickAccess({ profile }: { profile: ProfileT | null }) {
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
      <div className="mt-3 space-y-2.5">
        <QuickLink href={driveUrl} icon={<FolderOpen className="h-5 w-5" />} iconCls="bg-amber-50 text-amber-600"
          title="Drive folder" note={profile?.drive_folder_id ? "Your tax documents" : "Not linked — opens My Drive"} linked={!!profile?.drive_folder_id} />
        <QuickLink href={sheetsUrl} icon={<Table2 className="h-5 w-5" />} iconCls="bg-accent-50 text-accent-700"
          title="Results sheet" note={profile?.sheets_id ? "Findings & computed return" : "Not linked — opens Sheets"} linked={!!profile?.sheets_id} />
      </div>
    </div>
  );
}

function QuickLink({ href, icon, iconCls, title, note, linked }: {
  href: string; icon: React.ReactNode; iconCls: string; title: string; note: string; linked: boolean;
}) {
  return (
    <a href={href} target="_blank" rel="noreferrer"
      className="group flex items-center justify-between rounded-xl border border-line px-4 py-3 transition-colors hover:border-accent-200 hover:bg-accent-50/40">
      <span className="flex items-center gap-3">
        <span className={`grid h-9 w-9 place-items-center rounded-lg ${iconCls}`}>{icon}</span>
        <span>
          <span className="block text-sm font-medium text-ink-900">{title}</span>
          <span className={`block text-xs ${linked ? "text-ink-400" : "text-amber-600"}`}>{note}</span>
        </span>
      </span>
      <ExternalLink className="h-4 w-4 text-ink-400 group-hover:text-accent-700" />
    </a>
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
      <p className="mt-1 text-xs text-ink-400">Feedback is anonymous and stripped of personal data.</p>
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

// ── "?" help: how the user interacts with the system ──────────────────────────
const HELP_STEPS = [
  { t: "Connect your documents", d: "Link the Google Drive folder with your Form 16, AIS, 26AS and any capital-gains statements. The agent scans it and reads the figures for you." },
  { t: "Run the filing agent", d: "Press “Run filing agent”. It works through each task — identity, income, deductions — and shows every step live in the activity feed." },
  { t: "Confirm by email", d: "The agent emails you the figures it found and waits. Reply CONFIRM to approve, or DENY to stop. Nothing is finalised without your reply." },
  { t: "Review your return", d: "Check the “Computed return” panel. Your tax is calculated from the official slab rates — no AI guesses — so you can see exactly how the numbers add up." },
  { t: "Download & e-file", d: "Once every task is verified, “Export ITR JSON” unlocks. Download the file and upload it at the income-tax portal to finish filing." },
];

function HelpModal({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4" onClick={onClose} role="dialog" aria-modal="true" aria-label="How to use TaxAssist">
      <div className="card w-full max-w-md p-6 shadow-lift" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-bold text-ink-900">How to use TaxAssist</h2>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-ink-400 hover:bg-page hover:text-ink-900" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        <ol className="mt-5 space-y-4">
          {HELP_STEPS.map((s, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent-600 text-xs font-bold text-white">{i + 1}</span>
              <div>
                <p className="text-sm font-semibold text-ink-900">{s.t}</p>
                <p className="mt-0.5 text-sm leading-relaxed text-ink-500">{s.d}</p>
              </div>
            </li>
          ))}
        </ol>
        <p className="mt-5 flex items-start gap-2 rounded-lg bg-page p-3 text-xs leading-relaxed text-ink-500">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent-600" />
          Your name, PAN and account numbers are replaced with placeholders before the AI sees anything. Your real financial data never leaves the secure local layer unmasked.
        </p>
      </div>
    </div>
  );
}
