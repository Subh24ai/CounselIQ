import { ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-12">
      {/* Subtle layered gradient backdrop. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,hsl(var(--primary)/0.12),transparent_55%)]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_bottom,transparent,hsl(var(--background)))]"
      />

      <div className="relative z-10 mb-8 flex flex-col items-center text-center">
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 ring-1 ring-primary/20">
          <ShieldCheck className="h-7 w-7 text-primary" aria-hidden />
        </div>
        <span className="text-2xl font-semibold tracking-tight">CounselIQ</span>
        <span className="mt-1 text-sm text-muted-foreground">
          Legal Compliance Intelligence
        </span>
      </div>

      <div className="relative z-10 w-full max-w-md">{children}</div>
    </div>
  );
}
