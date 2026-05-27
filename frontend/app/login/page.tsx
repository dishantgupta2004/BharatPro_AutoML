"use client";

import { CheckCircle2, Loader2, Mail, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/lib/auth-context";

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
    <div className="flex min-h-screen items-center justify-center bg-canvas-900 px-4">
      <div className="w-full max-w-md rounded-2xl border border-canvas-500 bg-canvas-800 p-8 shadow-elevate">
        <div className="mb-5 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-accent-500 to-accent-700 shadow-glow">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          <div>
            <div className="text-sm font-semibold text-fg-50">Unisole Empower</div>
            <div className="text-[10px] uppercase tracking-wider text-fg-300">
              Distributed AutoML
            </div>
          </div>
        </div>

        {sent ? (
          <div className="rounded-xl border border-accent-500/30 bg-accent-500/10 p-4 text-sm text-fg-100">
            <div className="mb-2 flex items-center gap-2 font-semibold text-fg-50">
              <CheckCircle2 className="h-4 w-4 text-status-online" />
              Check your inbox
            </div>
            <p className="text-fg-200">
              We sent a magic link to <span className="font-mono">{email}</span>.
              Click it to sign in. The link expires in a few minutes.
            </p>
            <button
              onClick={() => {
                setSent(false);
                setEmail("");
              }}
              className="mt-3 text-[12px] text-accent-400 underline underline-offset-2 hover:text-accent-500"
            >
              Use a different email
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <h1 className="text-lg font-semibold text-fg-50">Sign in</h1>
            <p className="text-[13px] text-fg-200">
              Enter your email and we'll send you a one-time magic link.
            </p>
            <label className="block">
              <span className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-fg-300">
                Email
              </span>
              <div className="focus-ring flex items-center gap-2 rounded-lg border border-canvas-500 bg-canvas-900 px-3 py-2">
                <Mail className="h-3.5 w-3.5 text-fg-300" />
                <input
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full bg-transparent text-[14px] text-fg-50 placeholder:text-fg-300 focus:outline-none"
                />
              </div>
            </label>
            {error && (
              <div className="rounded-md border border-status-error/30 bg-status-error/10 p-2 text-[12px] text-status-error">
                {error}
              </div>
            )}
            <button
              type="submit"
              disabled={submitting}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent-600 px-3 py-2 text-[14px] font-medium text-white shadow-glow transition hover:bg-accent-500 disabled:cursor-not-allowed disabled:bg-canvas-600"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Sending…
                </>
              ) : (
                "Send magic link"
              )}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}