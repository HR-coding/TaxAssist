import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ShieldCheck, ScanLine, Mail, Calculator, Eye, EyeOff, Lock, FileCheck2,
  ArrowRight, PlayCircle, Check, X, Workflow, Bot, Gauge, ChevronRight,
} from "lucide-react";

const fade = {
  hidden: { opacity: 0, y: 14 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: i * 0.05, duration: 0.45, ease: "easeOut" } }),
};

const TRUST = [
  { icon: EyeOff, label: "AI never sees your PAN", note: "Personal data is tokenized before the model" },
  { icon: Calculator, label: "Deterministic math", note: "Computed from official slabs — no AI in the numbers" },
  { icon: Mail, label: "You approve everything", note: "Nothing is filed without your email confirmation" },
  { icon: Lock, label: "DPDP / GDPR erasure", note: "Encrypted tokens, full right-to-be-forgotten" },
];

const STEPS = [
  { n: "01", icon: ShieldCheck, t: "Connect Google", d: "Grant access to your Drive, Gmail, Sheets & Calendar.", see: "the exact scopes requested" },
  { n: "02", icon: ScanLine, t: "Agent reads your documents", d: "Detects Form 16 and extracts every figure with vision OCR.", see: "every figure it found, and where" },
  { n: "03", icon: Mail, t: "You confirm over email", d: "It emails you to approve the numbers; nothing moves until you reply.", see: "exactly what it's asking to do" },
  { n: "04", icon: Calculator, t: "Deterministic computation", d: "Tax is computed from government slabs — old vs new regime.", see: "the full computation, line by line" },
];

const CAN = [
  "Read your tax documents and extract figures",
  "Email you to confirm values and approvals",
  "Compute tax deterministically from official slabs",
  "Write the final result to your Google Sheet",
];
const CANNOT = [
  "See your real name, PAN, or account numbers",
  "Decide the workflow — a state machine does, not the AI",
  "Write or alter tax figures it didn't verify",
  "File or send anything without your approval",
];

const SECURITY = [
  { icon: Lock, t: "PII vault", d: "Names, PANs and IDs are replaced with synthetic tokens before the AI sees anything, and reconstructed only in the trusted local layer." },
  { icon: ShieldCheck, t: "Fail-closed gateway", d: "Every agent action passes a signed-identity, state-gated, intent-reconciled check before any data is touched." },
  { icon: Gauge, t: "Deterministic core", d: "The decider and tax calculators use no LLM. The AI proposes; the deterministic layer verifies and enforces." },
];

export default function Landing() {
  return (
    <div>
      {/* ── Hero ───────────────────────────────────────────────── */}
      <section className="relative overflow-hidden border-b border-line bg-paper">
        <div className="grid-faint pointer-events-none absolute inset-0" />
        <div className="container-x relative grid items-center gap-12 py-16 lg:grid-cols-[1.05fr_0.95fr] lg:py-24">
          <motion.div initial="hidden" animate="show" variants={fade}>
            <span className="chip border-accent-200 bg-accent-50 text-accent-900">
              <ShieldCheck className="h-3.5 w-3.5" /> ITR-1 &amp; ITR-2 · security-first
            </span>
            <h1 className="mt-5 font-display text-4xl font-extrabold leading-[1.08] tracking-tight text-ink-900 sm:text-5xl">
              Your income tax return, prepared by an agent you can{" "}
              <span className="text-accent-600">watch.</span>
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-ink-500">
              TaxAssist reads your documents, confirms every figure with you over email, and computes
              your tax deterministically from official slabs — then hands you a file-ready return, while
              the AI never sees your name or PAN.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link to="/login" className="btn-primary px-5 py-3 text-base">
                Start filing free <ArrowRight className="h-4 w-4" />
              </Link>
              <a href="#how" className="btn-secondary px-5 py-3 text-base">See how it works</a>
              <Link to="/login" className="btn-text ml-1">
                <PlayCircle className="h-5 w-5" /> Watch a live filing
              </Link>
            </div>
            <p className="mt-5 text-sm text-ink-400">
              No credit card · deterministic computation · you approve every step
            </p>
          </motion.div>

          {/* Live agent-activity peek */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.55 }}>
            <AgentPeek />
          </motion.div>
        </div>
      </section>

      {/* ── Trust signals strip ────────────────────────────────── */}
      <section id="trust" className="border-b border-line bg-page">
        <div className="container-x grid gap-px py-2 sm:grid-cols-2 lg:grid-cols-4">
          {TRUST.map((t, i) => (
            <motion.div key={t.label} custom={i} initial="hidden" whileInView="show" viewport={{ once: true }} variants={fade}
              className="flex items-start gap-3 px-4 py-5">
              <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent-50 text-accent-700">
                <t.icon className="h-5 w-5" />
              </span>
              <div>
                <p className="text-sm font-semibold text-ink-900">{t.label}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-ink-400">{t.note}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── How it works (the visible workflow) ────────────────── */}
      <section id="how" className="container-x py-20">
        <Head eyebrow="How it works" title="Four steps — and you can see each one"
          sub="Every step pairs what the agent does with what you can see, so the whole filing is auditable end to end." />
        <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <motion.div key={s.n} custom={i} initial="hidden" whileInView="show" viewport={{ once: true }} variants={fade}
              className="card p-6">
              <div className="flex items-center justify-between">
                <span className="grid h-10 w-10 place-items-center rounded-lg bg-accent-50 text-accent-700">
                  <s.icon className="h-5 w-5" />
                </span>
                <span className="font-display text-2xl font-bold text-line">{s.n}</span>
              </div>
              <h3 className="mt-4 font-display text-base font-semibold text-ink-900">{s.t}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-500">{s.d}</p>
              <p className="mt-4 flex items-start gap-2 border-t border-line pt-3 text-xs text-accent-700">
                <Eye className="mt-0.5 h-3.5 w-3.5 shrink-0" /> <span>You see {s.see}</span>
              </p>
            </motion.div>
          ))}
        </div>
        <div className="mt-6 flex items-center gap-3 rounded-2xl border border-accent-200 bg-accent-50 p-5">
          <Workflow className="h-5 w-5 shrink-0 text-accent-700" />
          <p className="text-sm leading-relaxed text-accent-900">
            The next step is always chosen by a <span className="font-semibold">deterministic state machine</span> —
            never the AI. The model can propose, but it can't steer the workflow off-course.
          </p>
        </div>
      </section>

      {/* ── Can / Can't (transparency) ─────────────────────────── */}
      <section className="border-y border-line bg-page py-20">
        <div className="container-x">
          <Head eyebrow="Transparency" title="What the agent can — and can never — do"
            sub="The deterministic layer is the enforcer. The AI is treated as untrusted reasoning and re-validated against state it can't influence." />
          <div className="mt-12 grid gap-5 lg:grid-cols-2">
            <div className="card p-7">
              <p className="flex items-center gap-2 font-display text-base font-semibold text-ink-900">
                <span className="grid h-7 w-7 place-items-center rounded-md bg-accent-50 text-accent-700"><Check className="h-4 w-4" /></span>
                The agent can
              </p>
              <ul className="mt-5 space-y-3">
                {CAN.map((c) => (
                  <li key={c} className="flex items-start gap-3 text-sm text-ink-600">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent-600" /> {c}
                  </li>
                ))}
              </ul>
            </div>
            <div className="card p-7">
              <p className="flex items-center gap-2 font-display text-base font-semibold text-ink-900">
                <span className="grid h-7 w-7 place-items-center rounded-md bg-ink-900/5 text-ink-700"><X className="h-4 w-4" /></span>
                The agent can never
              </p>
              <ul className="mt-5 space-y-3">
                {CANNOT.map((c) => (
                  <li key={c} className="flex items-start gap-3 text-sm text-ink-600">
                    <X className="mt-0.5 h-4 w-4 shrink-0 text-ink-400" /> {c}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ── Security architecture ──────────────────────────────── */}
      <section id="security" className="container-x py-20">
        <Head eyebrow="Security" title="Built so the AI is never trusted with your data" />
        <div className="mt-12 grid gap-5 lg:grid-cols-3">
          {SECURITY.map((s, i) => (
            <motion.div key={s.t} custom={i} initial="hidden" whileInView="show" viewport={{ once: true }} variants={fade}
              className="card p-7">
              <s.icon className="h-6 w-6 text-accent-600" />
              <h3 className="mt-3 font-display text-base font-semibold text-ink-900">{s.t}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-500">{s.d}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── Final CTA ──────────────────────────────────────────── */}
      <section className="container-x pb-24">
        <div className="overflow-hidden rounded-2xl border border-line bg-paper p-10 text-center shadow-card sm:p-14">
          <FileCheck2 className="mx-auto h-9 w-9 text-accent-600" />
          <h2 className="mx-auto mt-5 max-w-2xl font-display text-3xl font-extrabold tracking-tight text-ink-900">
            Get a file-ready return without touching a spreadsheet.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-ink-500">
            Create your first profile in under a minute and watch the agent work — every figure, every step, fully visible.
          </p>
          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <Link to="/login" className="btn-primary px-5 py-3 text-base">Start filing free <ArrowRight className="h-4 w-4" /></Link>
            <a href="#how" className="btn-secondary px-5 py-3 text-base">See how it works</a>
          </div>
        </div>
      </section>
    </div>
  );
}

function Head({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className="eyebrow">{eyebrow}</p>
      <h2 className="mt-3 font-display text-3xl font-extrabold tracking-tight text-ink-900 sm:text-[2.1rem]">{title}</h2>
      {sub && <p className="mt-4 leading-relaxed text-ink-500">{sub}</p>}
    </div>
  );
}

function AgentPeek() {
  const tasks = [
    { t: "Prerequisites", s: "Verified", tone: "done" },
    { t: "Salary · Form 16", s: "In review", tone: "review" },
    { t: "Deductions · 80C / 80D", s: "Pending", tone: "pending" },
  ];
  return (
    <div className="card overflow-hidden shadow-lift">
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
        <div className="flex items-center gap-2 text-sm">
          <span className="grid h-7 w-7 place-items-center rounded-full bg-accent-50 text-xs font-bold text-accent-700">A</span>
          <span className="font-medium text-ink-900">Anita Sharma</span>
          <span className="text-ink-400">· ITR-2</span>
        </div>
        <span className="chip border-amber-200 bg-amber-50 text-amber-700">Awaiting your reply</span>
      </div>
      <div className="space-y-2 px-5 py-4">
        {tasks.map((x) => (
          <div key={x.t} className="flex items-center justify-between rounded-lg border border-line px-3.5 py-2.5">
            <span className="text-sm text-ink-700">{x.t}</span>
            <span className={`chip ${
              x.tone === "done" ? "border-accent-200 bg-accent-50 text-accent-900"
              : x.tone === "review" ? "border-amber-200 bg-amber-50 text-amber-700"
              : "border-line bg-page text-ink-400"}`}>
              {x.tone === "done" && <Check className="h-3 w-3" />} {x.s}
            </span>
          </div>
        ))}
      </div>
      <div className="border-t border-line bg-page px-5 py-4">
        <p className="flex items-start gap-2 text-sm text-ink-600">
          <Bot className="mt-0.5 h-4 w-4 shrink-0 text-accent-600" />
          <span><span className="font-semibold text-ink-900">Agent:</span> Extracted Form 16 → gross salary <span className="font-medium text-ink-900">₹12,40,000</span>. Emailed you to confirm.</span>
        </p>
        <p className="mt-2.5 flex items-center gap-2 text-xs text-ink-400">
          <ChevronRight className="h-3.5 w-3.5 text-accent-600" />
          Next step: <code className="rounded bg-accent-50 px-1.5 py-0.5 text-accent-700">RECONCILE_AIS_TIS</code> · deterministic
        </p>
      </div>
    </div>
  );
}
