"use client";

import { BarChart3, Brain, FileSpreadsheet, Sparkles } from "lucide-react";

interface Props {
  hasActiveFile: boolean;
  onSuggestion: (text: string) => void;
}

const SUGGESTIONS = [
  {
    icon: FileSpreadsheet,
    title: "Peek at the data",
    prompt: "Show me the first 5 rows and the column types.",
  },
  {
    icon: BarChart3,
    title: "Generate an EDA report",
    prompt: "Run an EDA report on my dataset and summarize the key findings.",
  },
  {
    icon: Sparkles,
    title: "Visualize a column",
    prompt: "Plot a correlation heatmap for the numeric columns.",
  },
  {
    icon: Brain,
    title: "Train a baseline model",
    prompt: "Train a baseline Random Forest. The target column is …",
  },
];

export default function EmptyState({ hasActiveFile, onSuggestion }: Props) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 py-10 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-soft">
        <Brain className="h-7 w-7" />
      </div>
      <h1 className="mt-4 text-2xl font-semibold text-ink-900">
        Chat with your dataset
      </h1>
      <p className="mt-1 max-w-md text-sm text-ink-500">
        Upload a CSV on the left, then ask questions. The assistant calls local MCP
        tools to read the file, run EDA, plot charts, and train baseline models.
      </p>

      {!hasActiveFile && (
        <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          No active dataset selected — upload one first or ask the assistant to list available files.
        </div>
      )}

      <div className="mt-8 grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s.title}
            onClick={() => onSuggestion(s.prompt)}
            className="group flex items-start gap-3 rounded-xl border border-ink-200 bg-white p-4 text-left shadow-soft transition hover:border-brand-400 hover:bg-brand-50/40"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600 group-hover:bg-brand-100">
              <s.icon className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-ink-900">{s.title}</div>
              <div className="mt-0.5 truncate text-xs text-ink-500">{s.prompt}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
