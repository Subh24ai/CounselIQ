import Link from "next/link";
import { ShieldCheck, ScanLine, FileSearch } from "lucide-react";

const features = [
  {
    icon: FileSearch,
    title: "Document Intelligence",
    description:
      "Upload contracts and filings. Textract OCR plus pgvector retrieval make every page searchable.",
  },
  {
    icon: ScanLine,
    title: "Multi-Agent Analysis",
    description:
      "LangGraph agents reason over Indian statutes to surface compliance gaps and obligations.",
  },
  {
    icon: ShieldCheck,
    title: "Auditable Risk Flags",
    description:
      "Every risk is cited, severity-ranked, and recorded in an immutable audit trail.",
  },
];

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col items-center justify-center gap-12 px-6 py-16">
      <section className="text-center">
        <p className="mb-3 text-sm font-medium uppercase tracking-widest text-primary">
          CounselIQ
        </p>
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Legal compliance, continuously reviewed.
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
          A production-grade multi-agent AI platform that reads your legal
          documents, checks them against Indian regulation, and flags risk
          before it reaches your board.
        </p>
        <div className="mt-8 flex justify-center gap-4">
          <Link
            href="/login"
            className="inline-flex h-11 items-center rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Sign in
          </Link>
        </div>
      </section>

      <section className="grid w-full gap-6 sm:grid-cols-3">
        {features.map(({ icon: Icon, title, description }) => (
          <div
            key={title}
            className="rounded-lg border bg-card p-6 text-card-foreground"
          >
            <Icon className="mb-4 h-8 w-8 text-primary" aria-hidden />
            <h2 className="mb-2 text-lg font-semibold">{title}</h2>
            <p className="text-sm text-muted-foreground">{description}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
