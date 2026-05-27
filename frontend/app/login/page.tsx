"use client";

import {
  BarChart3,
  Brain,
  CheckCircle2,
  Cpu,
  FileText,
  Layers,
  Loader2,
  Lock,
  Mail,
  Network,
  Sparkles,
  Zap,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/lib/auth-context";

const FEATURES = [
  {
    icon: BarChart3,
    title: "Dataset Profiling & EDA",
    desc: "Auto-generated statistical summaries, correlation matrices, distribution plots, and missing-value analysis.",
  },
  {
    icon: Brain,
    title: "AutoML Bake-off",
    desc: "Parallel CV race across Random Forest, XGBoost, LightGBM, and baseline — champion selected automatically.",
  },
  {
    icon: Cpu,
    title: "Hyperparameter Sweeps",
    desc: "Optuna TPE search with time-budget control. Tune any champion model without writing a single line.",
  },
  {
    icon: Zap,
    title: "SHAP Explainability",
    desc: "Tree and kernel SHAP values, feature importance charts, and model explainability cards.",
  },
  {
    icon: FileText,
    title: "Notebook & PDF Export",
    desc: "Runnable Jupyter notebooks and polished PDF reports generated and uploaded for every pipeline run.",
  },
  {
    icon: Network,
    title: "5 MCP Microservices",
    desc: "Data · EDA · Modeling · Explain · Export — each independently scalable, live-monitored in the UI.",
  },
];

const STATS = [
  { value: "5", label: "MCP services" },
  { value: "4+", label: "ML frameworks" },
  { value: "∞", label: "Datasets" },
];

export default function LoginPage() {
  const router = useRouter();
  const { session, loading, signInWithOtp } = useAuth();
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && session) router.replace("/");
  }, [loading, session, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!email.trim()) {
      setError("Enter your email.");
      return;
    }
    setSubmitting(true);
    const { error: err } = await signInWithOtp(email.trim());
    setSubmitting(false);
    if (err) setError(err);
    else setSent(true);
  };

  return (
    <div className="flex min-h-screen bg-canvas-900">
      {/* ── LEFT HERO ─────────────────────────────────────────── */}
      <div className="relative hidden flex-col justify-between overflow-hidden px-12 py-12 lg:flex lg:w-[58%]">
        {/* Background glow */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(ellipse 900px 700px at 20% 30%, rgba(99,102,241,0.14) 0%, transparent 70%), " +
              "radial-gradient(ellipse 600px 400px at 80% 80%, rgba(139,92,246,0.08) 0%, transparent 60%)",
          }}
        />
        <div
          className="pointer-events-none absolute inset-0 opacity-20"
          style={{
            backgroundImage:
              "linear-gradient(rgba(99,102,241,0.06) 1px, transparent 1px), " +
              "linear-gradient(90deg, rgba(99,102,241,0.06) 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />

        {/* Top brand */}
        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-accent-500 to-accent-700 shadow-glow">
              <Layers className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="text-sm font-bold tracking-tight text-fg-50">NSK AI Labs</div>
              <div className="text-[10px] uppercase tracking-widest text-fg-300">
                MetaOptics · AI Research
              </div>
            </div>
          </div>
        </div>

        {/* Main hero copy */}
        <div className="relative z-10 max-w-xl">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-accent-500/25 bg-accent-500/8 px-3 py-1.5 text-[11px] font-medium text-accent-300">
            <Sparkles className="h-3 w-3" />
            AI-native AutoML · Powered by 5 MCP Microservices
          </div>

          <h1 className="mb-4 text-5xl font-extrabold leading-[1.1] tracking-tight text-fg-50">
            BharatPro
            <br />
            <span className="bg-gradient-to-r from-accent-400 via-violet-400 to-purple-400 bg-clip-text text-transparent">
              AutoML
            </span>
          </h1>

          <p className="mb-6 text-lg leading-relaxed text-fg-200">
            Production-grade machine learning pipelines through conversation.
            Upload a CSV, describe your goal, and the platform ships real
            models, notebooks, and reports — no code required.
          </p>

          {/* Stats row */}
          <div className="mb-10 flex gap-6">
            {STATS.map((s) => (
              <div key={s.label}>
                <div className="text-2xl font-bold text-fg-50">{s.value}</div>
                <div className="text-[11px] text-fg-300">{s.label}</div>
              </div>
            ))}
          </div>

          {/* Feature grid */}
          <div className="grid grid-cols-2 gap-3">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <div
                  key={f.title}
                  className="rounded-xl border border-canvas-500/60 bg-canvas-800/50 p-3.5 backdrop-blur-sm transition hover:border-accent-500/40 hover:bg-canvas-800/80"
                >
                  <div className="mb-2 flex items-center gap-2">
                    <div className="flex h-6 w-6 items-center justify-center rounded-md bg-accent-500/15">
                      <Icon className="h-3.5 w-3.5 text-accent-400" />
                    </div>
                    <span className="text-[12px] font-semibold text-fg-50">{f.title}</span>
                  </div>
                  <p className="text-[11px] leading-relaxed text-fg-300">{f.desc}</p>
                </div>
              );
            })}
          </div>
        </div>

        {/* Bottom org info */}
        <div className="relative z-10 flex items-center justify-between">
          <div className="flex items-center gap-3 text-[11px] text-fg-400">
            <Lock className="h-3 w-3" />
            <span>Supabase auth · JWT secured · Data stays yours</span>
          </div>
          <a
            href="https://sites.google.com/nskailabs.com/nskailabs/home"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] text-fg-400 underline decoration-fg-500/40 underline-offset-2 hover:text-fg-200"
          >
            nskailabs.com
          </a>
        </div>
      </div>

      {/* ── RIGHT AUTH PANEL ──────────────────────────────────── */}
      <div className="flex w-full items-center justify-center px-6 py-12 lg:w-[42%] lg:border-l lg:border-canvas-500 lg:bg-canvas-800/30">
        <div className="w-full max-w-sm">
          {/* Mobile brand (shown only on small screens) */}
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-accent-500 to-accent-700 shadow-glow">
              <Layers className="h-4 w-4 text-white" />
            </div>
            <div>
              <div className="text-sm font-bold text-fg-50">NSK AI Labs</div>
              <div className="text-[10px] uppercase tracking-wider text-fg-300">BharatPro AutoML</div>
            </div>
          </div>

          <div className="mb-8">
            <h2 className="text-2xl font-bold text-fg-50">Sign in</h2>
            <p className="mt-1.5 text-sm text-fg-300">
              Enter your email — we&apos;ll send a one-time magic link.
            </p>
          </div>

          {sent ? (
            <div className="rounded-2xl border border-accent-500/30 bg-accent-500/8 p-5">
              <div className="mb-3 flex items-center gap-2 font-semibold text-fg-50">
                <CheckCircle2 className="h-5 w-5 text-status-online" />
                Check your inbox
              </div>
              <p className="mb-4 text-sm text-fg-200">
                A magic link was sent to{" "}
                <span className="font-mono text-fg-50">{email}</span>.
                Click it to sign in — it expires in a few minutes.
              </p>
              <button
                onClick={() => { setSent(false); setEmail(""); }}
                className="text-[12px] text-accent-400 underline underline-offset-2 hover:text-accent-300"
              >
                Use a different email
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-fg-300">
                  Email address
                </span>
                <div className="flex items-center gap-2.5 rounded-xl border border-canvas-500 bg-canvas-900/80 px-3.5 py-3 transition focus-within:border-accent-500/60 focus-within:ring-1 focus-within:ring-accent-500/30">
                  <Mail className="h-4 w-4 shrink-0 text-fg-300" />
                  <input
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full bg-transparent text-sm text-fg-50 placeholder:text-fg-400 focus:outline-none"
                  />
                </div>
              </label>

              {error && (
                <div className="rounded-lg border border-status-error/30 bg-status-error/10 p-3 text-[12px] text-status-error">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent-600 px-4 py-3 text-sm font-semibold text-white shadow-glow transition hover:bg-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/50 disabled:cursor-not-allowed disabled:bg-canvas-600 disabled:shadow-none"
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Sending…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    Send magic link
                  </>
                )}
              </button>
            </form>
          )}

          <div className="mt-8 space-y-2 rounded-xl border border-canvas-500/50 bg-canvas-800/40 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-fg-400">
              Platform highlights
            </div>
            {[
              "No code required — plain English pipelines",
              "Groq Llama-3.3-70B routes all tool decisions",
              "Real downloadable artifacts every run",
            ].map((t) => (
              <div key={t} className="flex items-start gap-2 text-[12px] text-fg-300">
                <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-accent-400" />
                {t}
              </div>
            ))}
          </div>

          <p className="mt-6 text-center text-[11px] text-fg-400">
            NSK AI Labs ·{" "}
            <a
              href="mailto:admin@nskailabs.com"
              className="text-accent-400 hover:text-accent-300"
            >
              admin@nskailabs.com
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
