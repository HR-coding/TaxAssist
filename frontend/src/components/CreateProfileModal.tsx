import { FormEvent, useState } from "react";
import { X } from "lucide-react";
import { api } from "../lib/api";
import { Spinner } from "./ui";

export default function CreateProfileModal({
  open, onClose, onCreated,
}: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [relation, setRelation] = useState("self");
  const [itr, setItr] = useState("ITR1");
  const [drive, setDrive] = useState("");
  const [sheet, setSheet] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (!open) return null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) { setErr("Enter a display name."); return; }
    setBusy(true); setErr("");
    try {
      await api.createProfile({
        display_name: name.trim(), relation, itr_type: itr,
        drive_folder_id: drive.trim(), sheets_id: sheet.trim(),
      } as any);
      setName(""); setDrive(""); setSheet(""); setRelation("self"); setItr("ITR1");
      onCreated();
    } catch (e: any) {
      setErr(e.message || "Failed to create profile");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink-900/30 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="card w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold text-ink-900">New filing profile</h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-ink-400 hover:bg-page hover:text-ink-900" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={submit} className="mt-5 space-y-4">
          <div>
            <label className="label">Display name</label>
            <input className="input mt-1.5" placeholder="e.g. Anita Sharma" value={name}
              onChange={(e) => { setName(e.target.value); setErr(""); }} autoFocus />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Relation</label>
              <select className="input mt-1.5" value={relation} onChange={(e) => setRelation(e.target.value)}>
                <option value="self">Self</option>
                <option value="spouse">Spouse</option>
                <option value="dependent">Dependent</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className="label">ITR type</label>
              <select className="input mt-1.5" value={itr} onChange={(e) => setItr(e.target.value)}>
                <option value="ITR1">ITR-1 (Sahaj)</option>
                <option value="ITR2">ITR-2</option>
              </select>
            </div>
          </div>
          <div>
            <label className="label">Drive folder ID <span className="font-normal normal-case text-ink-400">(optional)</span></label>
            <input className="input mt-1.5" placeholder="Folder the agent reads documents from" value={drive}
              onChange={(e) => setDrive(e.target.value)} />
          </div>
          <div>
            <label className="label">Google Sheet ID <span className="font-normal normal-case text-ink-400">(optional)</span></label>
            <input className="input mt-1.5" placeholder="Sheet the agent writes results to" value={sheet}
              onChange={(e) => setSheet(e.target.value)} />
          </div>

          {err && <p className="text-xs text-red-600">{err}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy && <Spinner />} Create profile
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
