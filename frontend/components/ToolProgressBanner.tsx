"use client";

import { Loader2, Wrench } from "lucide-react";

import type { ActiveToolBadge } from "@/lib/types";

interface Props {
  badge: ActiveToolBadge;
}

export default function ToolProgressBanner({ badge }: Props) {
  const pct = Math.max(0, Math.min(100, badge.percentage));
  return (
    <div className="flex items-center gap-3 rounded-lg border border-accent-500/30 bg-accent-500/10 px-3 py-2 text-[11px] text-fg-100 shadow-ring">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-accent-600 text-white">
        <Wrench className="h-3 w-3" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 font-semibold text-fg-50">
          <Loader2 className="h-3 w-3 animate-spin text-accent-400" />
          Calling <code className="font-mono text-accent-400">{badge.name}</code>
          {badge.service && (
            <span className="rounded bg-canvas-700 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-300">
              {badge.service}
            </span>
          )}
        </div>
        <div className="truncate text-[10px] text-fg-200">{badge.message}</div>
        {pct > 0 && (
          <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-canvas-700">
            <div
              className="h-full bg-accent-500 transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
      </div>
    </div>
  );
}