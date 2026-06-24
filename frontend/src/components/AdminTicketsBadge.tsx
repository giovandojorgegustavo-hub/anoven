/**
 * AdminTicketsBadge — badge de tickets no leídos para el panel admin.
 *
 * Polling cada 30s a GET /api/admin/tickets/unread-count.
 * AbortController per request — cleanup en unmount.
 * Muestra badge con conteo si count > 0 (color accent/terracotta D3.1).
 * Oculto si count = 0.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { API_URL } from "@/lib/config";
import { getToken } from "@/lib/auth";

const POLL_INTERVAL_MS = 30_000;

export default function AdminTicketsBadge() {
  const [count, setCount] = useState(0);
  const cancelledRef = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    cancelledRef.current = false;

    async function fetchCount() {
      const token = getToken();
      if (!token) return;

      // Abort previous in-flight request
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      try {
        const res = await fetch(`${API_URL}/api/admin/tickets/unread-count`, {
          signal: controller.signal,
          headers: { Authorization: `Bearer ${token}` },
        });
        if (cancelledRef.current) return;
        if (!res.ok) return; // silently skip on auth errors (403/401)
        const data = await res.json();
        if (cancelledRef.current) return;
        setCount(data.count ?? 0);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") return;
        // On network error, keep previous count — don't reset badge
      }
    }

    fetchCount();
    const id = setInterval(fetchCount, POLL_INTERVAL_MS);

    return () => {
      cancelledRef.current = true;
      controllerRef.current?.abort();
      clearInterval(id);
    };
  }, []);

  if (count <= 0) return null;

  return (
    <Link
      href="/admin/tickets?status=open"
      className="inline-flex items-center gap-1.5 rounded-full bg-accent px-3 py-1 text-xs font-medium text-paper hover:opacity-90"
      title={`${count} ticket${count === 1 ? "" : "s"} sin revisar`}
    >
      <span>{count}</span>
      <span>{count === 1 ? "ticket pendiente" : "tickets pendientes"}</span>
    </Link>
  );
}
