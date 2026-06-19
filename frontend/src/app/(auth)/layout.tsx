import { FileSearch, Radar, ShieldAlert, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

const FEATURES = [
  {
    icon: FileSearch,
    title: "Automated clause extraction",
    description: "Five specialist agents read every contract end to end.",
  },
  {
    icon: ShieldAlert,
    title: "Risk scoring you can defend",
    description: "Every flag is graded, explained and traced to its source.",
  },
  {
    icon: Radar,
    title: "Live regulatory monitoring",
    description: "Know the moment a rule change touches your documents.",
  },
];

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* ---------------------------------------------------------------- */}
      {/* Left: branded value panel (desktop only).                        */}
      {/* ---------------------------------------------------------------- */}
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-primary p-12 text-primary-foreground lg:flex">
        {/* Decorative layers. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,hsl(var(--primary-foreground)/0.18),transparent_55%)]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(hsl(var(--primary-foreground))_1px,transparent_1px),linear-gradient(90deg,hsl(var(--primary-foreground))_1px,transparent_1px)] [background-size:36px_36px]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-24 -left-24 h-72 w-72 rounded-full bg-primary-foreground/10 blur-3xl"
        />

        {/* Wordmark. */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-foreground/15 ring-1 ring-inset ring-primary-foreground/25">
            <ShieldCheck className="h-6 w-6" aria-hidden />
          </div>
          <div className="leading-tight">
            <div className="text-lg font-semibold tracking-tight">CounselIQ</div>
            <div className="text-xs text-primary-foreground/70">
              Legal Compliance Intelligence
            </div>
          </div>
        </div>

        {/* Headline + features. */}
        <div className="relative z-10 max-w-md">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight">
            Turn dense contracts into clear, defensible decisions.
          </h1>
          <p className="mt-3 text-sm text-primary-foreground/80">
            CounselIQ reads, scores and monitors your legal documents so your
            team spends time on judgement, not page-turning.
          </p>

          <ul className="mt-10 space-y-6">
            {FEATURES.map(({ icon: Icon, title, description }) => (
              <li key={title} className="flex gap-4">
                <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-foreground/10 ring-1 ring-inset ring-primary-foreground/20">
                  <Icon className="h-[18px] w-[18px]" aria-hidden />
                </div>
                <div>
                  <div className="text-sm font-medium">{title}</div>
                  <div className="text-sm text-primary-foreground/70">
                    {description}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>

        {/* Footer trust line. */}
        <p className="relative z-10 text-xs text-primary-foreground/60">
          Bank-grade encryption · Role-based access · Full audit trail
        </p>
      </aside>

      {/* ---------------------------------------------------------------- */}
      {/* Right: form column (with a compact brand header on mobile).       */}
      {/* ---------------------------------------------------------------- */}
      <main className="relative flex flex-col items-center justify-center px-4 py-10 sm:px-6">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,hsl(var(--primary)/0.06),transparent_60%)] lg:hidden"
        />

        {/* Mobile-only logo (the panel is hidden below lg). */}
        <div className="relative z-10 mb-8 flex flex-col items-center text-center lg:hidden">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 ring-1 ring-primary/20">
            <ShieldCheck className="h-7 w-7 text-primary" aria-hidden />
          </div>
          <span className="text-2xl font-semibold tracking-tight">
            CounselIQ
          </span>
          <span className="mt-1 text-sm text-muted-foreground">
            Legal Compliance Intelligence
          </span>
        </div>

        <div className="relative z-10 w-full max-w-md">{children}</div>
      </main>
    </div>
  );
}
