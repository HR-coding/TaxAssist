import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, UserPlus, ChevronRight, FolderOpen, Sparkles } from "lucide-react";
import { api, Profile } from "../lib/api";
import { useAuth } from "../lib/auth";
import { PageLoader } from "../components/ui";
import CreateProfileModal from "../components/CreateProfileModal";

const RELATION_LABEL: Record<string, string> = {
  self: "Self", spouse: "Spouse", dependent: "Dependent", other: "Other",
};

export default function Dashboard() {
  const { email } = useAuth();
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState("");

  async function load() {
    try {
      const me = await api.me();
      setProfiles(me.profiles);
    } catch (e: any) {
      setErr(e.message || "Failed to load");
      setProfiles([]);
    }
  }
  useEffect(() => { load(); }, []);

  return (
    <div className="container-x py-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h1 className="mt-2 font-display text-3xl font-extrabold tracking-tight text-ink-900">Your filing profiles</h1>
          <p className="mt-1 text-sm text-ink-400">Signed in as {email}</p>
        </div>
        <button className="btn-primary" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> New profile
        </button>
      </div>

      {err && <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{err}</div>}

      {profiles === null ? (
        <PageLoader label="Loading profiles" />
      ) : profiles.length === 0 ? (
        <EmptyState onCreate={() => setOpen(true)} />
      ) : (
        <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {profiles.map((p) => (
            <Link key={p.id} to={`/app/profile/${p.id}`}
              className="card group flex flex-col p-6 transition-all hover:-translate-y-0.5 hover:shadow-lift">
              <div className="flex items-center justify-between">
                <div className="grid h-11 w-11 place-items-center rounded-xl bg-accent-50 text-lg font-bold text-accent-700">
                  {p.display_name.charAt(0).toUpperCase()}
                </div>
                <span className="chip border-line bg-page text-ink-600">{p.itr_type}</span>
              </div>
              <h3 className="mt-4 font-display text-lg font-semibold text-ink-900">{p.display_name}</h3>
              <p className="text-sm text-ink-400">{RELATION_LABEL[p.relation] ?? p.relation}</p>
              <div className="mt-5 flex items-center justify-between border-t border-line pt-4 text-sm">
                <span className="inline-flex items-center gap-1.5 text-ink-500"><FolderOpen className="h-4 w-4" /> Open workspace</span>
                <ChevronRight className="h-4 w-4 text-ink-400 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>
          ))}
        </div>
      )}

      <CreateProfileModal open={open} onClose={() => setOpen(false)} onCreated={() => { setOpen(false); setProfiles(null); load(); }} />
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="card mt-10 flex flex-col items-center px-6 py-16 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-2xl bg-accent-50 text-accent-700">
        <UserPlus className="h-7 w-7" />
      </div>
      <h3 className="mt-5 font-display text-xl font-semibold text-ink-900">Create your first profile</h3>
      <p className="mt-2 max-w-sm text-sm leading-relaxed text-ink-500">
        A profile is one filer — you, your spouse, a dependent. Each is an isolated tenant with its own
        documents, tasks, and agent runs.
      </p>
      <button className="btn-primary mt-6" onClick={onCreate}>
        <Sparkles className="h-4 w-4" /> Create profile
      </button>
    </div>
  );
}
