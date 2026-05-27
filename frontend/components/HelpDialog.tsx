"use client";

import { Mail, Sparkles, X } from "lucide-react";
import { useEffect } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
}

const SUPPORT_EMAIL = "admin@nskailabs.com";

const QUICKSTART = [
  {
    title: "1. Upload your dataset",
    body: "Drop a CSV in the right-hand workspace. It's saved locally to the upload directory.",
  },
  {
    title: "2. Ask in plain English",
    body: "“Profile my dataset”, “Train a model — target is `species`, spend 1 minute tuning.”",
  },
  {
    title: "3. Drive multi-step flows with prompts",
    body: "Type `/` in the composer to run a native MCP prompt template like /eda-deep-dive.",
  },
  {
    title: "4. Inspect artifacts in the workspace",
    body: "Profile reports, SHAP charts, leaderboards, and notebooks land in the tabbed viewer on the right.",
  },
];

export default function HelpDialog({ open, onClose }: Props) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-canvas-900/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-lg rounded-2xl border border-canvas-500 bg-canvas-800 p-6 shadow-elevate animate-slide-in"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <button
          onClick={onClose}
          className="absolute right-3 top-3 rounded-md p-1 text-fg-300 hover:bg-canvas-600 hover:text-fg-100"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="mb-4 flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-accent-400" />
          <h2 className="text-lg font-semibold text-fg-50">Welcome to BharatPro AutoML</h2>
        </div>

        <p className="text-sm text-fg-200">
          NSK AI Labs BharatPro AutoML — an AI-native platform powered by five MCP
          microservices. Here&apos;s how to get started:
        </p>

        <div className="mt-4 space-y-3">
          {QUICKSTART.map((s) => (
            <div key={s.title} className="rounded-lg border border-canvas-500 bg-canvas-700/50 p-3">
              <div className="text-[13px] font-semibold text-fg-50">{s.title}</div>
              <div className="mt-0.5 text-[12px] text-fg-200">{s.body}</div>
            </div>
          ))}
        </div>

        <div className="mt-5 rounded-lg border border-accent-500/30 bg-accent-500/5 p-3">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-fg-50">
            <Mail className="h-4 w-4 text-accent-400" />
            Need help?
          </div>
          <p className="mt-1 text-[12px] text-fg-200">
            Reach NSK AI Labs at{" "}
            <a
              href={`mailto:${SUPPORT_EMAIL}`}
              className="font-mono text-accent-400 underline decoration-accent-500/40 underline-offset-2 hover:text-accent-500"
            >
              {SUPPORT_EMAIL}
            </a>
            . We typically reply within one business day.
          </p>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-md bg-accent-600 px-3 py-1.5 text-[13px] font-medium text-white shadow-glow hover:bg-accent-500"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}