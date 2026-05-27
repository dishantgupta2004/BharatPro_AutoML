"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  authedFetch,
  fetchServicesSnapshot,
  refreshServices,
  servicesStreamUrl,
} from "@/lib/api";
import type { ServicesSnapshot, ServiceState, ServiceStatus } from "@/lib/types";

interface UseServiceNetworkResult {
  snapshot: ServicesSnapshot | null;
  services: ServiceState[];
  loading: boolean;
  refresh: () => Promise<void>;
  countByStatus: Record<ServiceStatus, number>;
}

export function useServiceNetwork(): UseServiceNetworkResult {
  const [snapshot, setSnapshot] = useState<ServicesSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setSnapshot(await refreshServices());
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial snapshot
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await fetchServicesSnapshot();
        if (!cancelled) {
          setSnapshot(s);
          setLoading(false);
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Long-lived stream — fetch + ReadableStream (EventSource cannot set Authorization)
  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;

    const apply = (incoming: Partial<ServiceState> & { name: string }) => {
      setSnapshot((prev) => {
        if (!prev) return prev;
        const next = { ...prev, services: prev.services.map((s) => ({ ...s })) };
        const idx = next.services.findIndex((s) => s.name === incoming.name);
        if (idx >= 0) next.services[idx] = { ...next.services[idx], ...incoming };
        return next;
      });
    };

    (async () => {
      try {
        const res = await authedFetch(servicesStreamUrl(), {
          method: "GET",
          headers: { Accept: "text/event-stream" },
          signal: controller.signal,
          cache: "no-store",
        });
        if (!res.ok || !res.body) return;

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let sep = buffer.indexOf("\n\n");
          while (sep !== -1) {
            const rawFrame = buffer.slice(0, sep);
            buffer = buffer.slice(sep + 2);
            sep = buffer.indexOf("\n\n");

            const lines = rawFrame
              .split("\n")
              .filter((l) => l.startsWith("data:"))
              .map((l) => l.slice(5).replace(/^ /, ""));
            if (!lines.length) continue;

            try {
              const payload = JSON.parse(lines.join("\n"));
              if (payload.type === "snapshot") setSnapshot(payload.payload);
              else if (payload.type === "service_status" && payload.service) {
                apply(payload.service);
              }
            } catch (err) {
              console.warn("services SSE parse error", err);
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          console.warn("services stream ended:", err);
        }
      }
    })();

    return () => controller.abort();
  }, []);

  const services = snapshot?.services ?? [];
  const countByStatus: Record<ServiceStatus, number> = {
    online: 0,
    offline: 0,
    processing: 0,
    error: 0,
  };
  for (const s of services) countByStatus[s.status] = (countByStatus[s.status] || 0) + 1;

  return { snapshot, services, loading, refresh, countByStatus };
}