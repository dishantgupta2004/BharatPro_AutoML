"use client";

import { useEffect, useState, useCallback } from "react";

import {
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

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const s = await refreshServices();
      setSnapshot(s);
    } finally {
      setLoading(false);
    }
  }, []);

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

  // Subscribe to the long-lived SSE stream
  useEffect(() => {
    const url = servicesStreamUrl();
    const es = new EventSource(url);

    const apply = (incoming: Partial<ServiceState> & { name: string }) => {
      setSnapshot((prev) => {
        if (!prev) return prev;
        const next = { ...prev, services: prev.services.map((s) => ({ ...s })) };
        const idx = next.services.findIndex((s) => s.name === incoming.name);
        if (idx >= 0) {
          next.services[idx] = { ...next.services[idx], ...incoming };
        }
        return next;
      });
    };

    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data);
        if (payload.type === "snapshot") {
          setSnapshot(payload.payload);
        } else if (payload.type === "service_status" && payload.service) {
          apply(payload.service);
        }
      } catch (err) {
        console.warn("services SSE parse error", err);
      }
    };
    es.onerror = () => {
      // EventSource auto-reconnects; nothing to do but log silently.
    };

    return () => {
      es.close();
    };
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