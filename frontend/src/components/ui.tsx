import { ReactNode } from "react";
import { Check, Clock, Loader2, Minus, AlertTriangle, Mail } from "lucide-react";

export function Spinner({ className = "" }: { className?: string }) {
  return <Loader2 className={`h-4 w-4 animate-spin ${className}`} />;
}

export function PageLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-24 text-ink-400">
      <Spinner /> <span className="text-sm">{label}…</span>
    </div>
  );
}

const STATUS_STYLES: Record<string, { cls: string; icon: ReactNode; text: string }> = {
  done: { cls: "border-accent-200 bg-accent-50 text-accent-900", icon: <Check className="h-3.5 w-3.5" />, text: "Verified" },
  in_review: { cls: "border-amber-200 bg-amber-50 text-amber-700", icon: <Clock className="h-3.5 w-3.5" />, text: "In review" },
  pending: { cls: "border-line bg-page text-ink-500", icon: <Clock className="h-3.5 w-3.5" />, text: "Pending" },
  skipped: { cls: "border-line bg-paper text-ink-400", icon: <Minus className="h-3.5 w-3.5" />, text: "N/A" },
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  return (
    <span className={`chip ${s.cls}`}>
      {s.icon} {label ?? s.text}
    </span>
  );
}

const RUN_STYLES: Record<string, { cls: string; icon: ReactNode; text: string }> = {
  done: { cls: "border-accent-200 bg-accent-50 text-accent-900", icon: <Check className="h-3.5 w-3.5" />, text: "Completed" },
  running: { cls: "border-blue-200 bg-blue-50 text-blue-700", icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />, text: "Running" },
  queued: { cls: "border-line bg-page text-ink-500", icon: <Clock className="h-3.5 w-3.5" />, text: "Queued" },
  waiting_reply: { cls: "border-amber-200 bg-amber-50 text-amber-700", icon: <Mail className="h-3.5 w-3.5" />, text: "Awaiting your reply" },
  failed: { cls: "border-red-200 bg-red-50 text-red-700", icon: <AlertTriangle className="h-3.5 w-3.5" />, text: "Failed" },
};

export function RunBadge({ status }: { status: string }) {
  const s = RUN_STYLES[status] ?? RUN_STYLES.queued;
  return (
    <span className={`chip ${s.cls}`}>
      {s.icon} {s.text}
    </span>
  );
}

export function timeAgo(iso?: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}
