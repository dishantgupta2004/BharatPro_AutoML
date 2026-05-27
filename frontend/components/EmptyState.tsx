"use client";

import {
  BarChart3,
  Brain,
  FileText,
  Layers,
  Search,
  Sparkles,
} from "lucide-react";

interface Props {
  onSuggestion: (text: string) => void;
  hasActiveFile: boolean;
}

const SUGGESTIONS = [
  {
    icon: Search,
    title: "Profile my dataset",
    detail: "Run schema validation and a full EDA report.",
    text: "Validate the schema of my dataset, then generate a full EDA report with a correlation matrix.",
    services: ["mcp-data", "mcp-eda"],
  },
  {
    icon: BarChart3,
    title: "Train a baseline",
    detail: "Race Random Forest vs XGBoost vs LightGBM.",
    text: "Train a baseline classifier on my dataset — pick the target column from the schema and run a parallel bake-off.",
    services: ["mcp-modeling"],
  },
  {
    icon: Brain,
    title: "Explain the champion",
    detail: "SHAP values + feature importance card.",
    text: "After training, compute SHAP values for the champion and render a feature importance plot.",
    services: ["mcp-explain"],
  },
  {
    icon: FileText,
    title: "Ship the pipeline",
    detail: "Generate a runnable notebook + PDF report.",
    text: "Generate a Jupyter notebook reproducing my pipeline, then compile a PDF report with the leaderboard.",
    services: ["mcp-export"],
  },
];

export default function EmptyState({ onSuggestion, hasActiveFile }: Props) {
  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center px-6 py-10 text-center">
      <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-500 to-accent-700 shadow-glow">
        <Layers className="h-7 w-7 text-white" />
      </div>

      <div className="mb-1 inline-flex items-center gap-1.5 rounded-full border border-canvas-500 bg-canvas-800 px-3 py-1 text-[10px] uppercase tracking-wider text-fg-300">
        <Sparkles className="h-3 w-3 text-accent-400" />
        NSK AI Labs · 5 MCP services
      </div>

      <h1 className="mt-3 text-2xl font-semibold text-fg-50">
        BharatPro AutoML
      </h1>
      <p className="mt-1.5 max-w-md text-[13px] text-fg-200">
        Your AI copilot orchestrates data, EDA, modeling, explainability, and
        export microservices over MCP — ask in plain English, get production
        artifacts.
      </p>

      {!hasActiveFile && (
        <div className="mt-4 rounded-lg border border-accent-500/30 bg-accent-500/5 px-3 py-2 text-[12px] text-fg-100">
          <span className="font-semibold text-fg-50">Tip:</span> Upload a CSV in
          the right panel to get started.
        </div>
      )}

      <div className="mt-6 grid w-full grid-cols-1 gap-2.5 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => {
          const Icon = s.icon;
          return (
            <button
              key={s.title}
              onClick={() => onSuggestion(s.text)}
              className="group flex flex-col gap-1.5 rounded-xl border border-canvas-500 bg-canvas-800/60 p-3 text-left transition hover:-translate-y-0.5 hover:border-accent-500/60 hover:bg-canvas-800 hover:shadow-glow"
            >
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-canvas-700 text-accent-400 group-hover:bg-accent-500/15">
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <span className="text-[13px] font-semibold text-fg-50">
                  {s.title}
                </span>
              </div>
              <p className="text-[11px] text-fg-200">{s.detail}</p>
              <div className="flex flex-wrap gap-1">
                {s.services.map((svc) => (
                  <span
                    key={svc}
                    className="rounded bg-canvas-900 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-300"
                  >
                    {svc}
                  </span>
                ))}
              </div>
            </button>
          );
        })}
      </div>

      <div className="mt-6 text-[10px] text-fg-300">
        Press <kbd>/</kbd> in the composer to discover prompt commands.
      </div>
    </div>
  );
}