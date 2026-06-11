import { Logo } from "./Navbar";

export default function Footer() {
  return (
    <footer className="mt-24 border-t border-line bg-paper">
      <div className="container-x flex flex-col gap-6 py-10 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-3">
          <Logo />
          <p className="max-w-sm text-sm text-ink-500">
            Autonomous ITR-1 &amp; ITR-2 filing for India — the AI is treated as untrusted,
            the math is deterministic, and you approve every step.
          </p>
        </div>
        <div className="text-sm text-ink-400">
          <p>Grounded in official slabs · DPDP/GDPR erasure built in</p>
          <p className="mt-1">© {new Date().getFullYear()} TaxAssist · Apache-2.0</p>
        </div>
      </div>
    </footer>
  );
}
