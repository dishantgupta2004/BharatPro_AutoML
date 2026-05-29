"use client";

import { Loader2 } from "lucide-react";

import type { ActiveToolBadge } from "@/lib/types";

interface Props {
  badge: ActiveToolBadge;
}

export default function ToolProgressBanner({ badge }: Props) {
  const pct = Math.max(0, Math.min(100, badge.percentage));
  return (
    <div className="flex items-center gap-3 rounded-lg border border-accent-500/30 bg-accent-500/10 px-3 py-2 text-[11px] text-fg-100 shadow-ring">
      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-accent-400" />
      <div className="min-w-0 flex-1">
        <div className="font-semibold text-fg-50">{badge.label}</div>
        {badge.message && badge.message !== `${badge.label}…` && (
          <div className="truncate text-[10px] text-fg-300">{badge.message}</div>
        )}
        {pct > 0 && (
          <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-canvas-700">
            <div
              className="h-full bg-accent-500 transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
