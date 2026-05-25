"use client";

import { Loader2, Wrench } from "lucide-react";

import type { ActiveToolBadge } from "@/lib/types";

interface Props {
  badge: ActiveToolBadge;
}

export default function ToolProgressBanner({ badge }: Props) {
  const pct = Math.max(0, Math.min(100, badge.percentage));
  return (
    <div className="flex items-center gap-3 rounded-xl border border-brand-200 bg-brand-50/70 px-3 py-2 text-xs text-brand-800 shadow-soft">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-brand-600 text-white">
        <Wrench className="h-3.5 w-3.5" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 font-semibold">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Calling <code className="font-mono">{badge.name}</code>
        </div>
        <div className="truncate text-[11px] text-brand-700">{badge.message}</div>
        {pct > 0 && (
          <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-brand-100">
            <div
              className="h-full bg-brand-600 transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
      </div>
    </div>
  );
}