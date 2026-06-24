/**
 * InvitationsBadge — badge de invitaciones pendientes en el header.
 *
 * Polling cada 30s a GET /api/projects/invitations/unread-count.
 * AbortController por request + cleanup on unmount (ADR-6).
 * Muestra badge si count > 0 (color accent/terracotta D3.1).
 * Oculto si count = 0.
 *
 * "use client" justificado (A2.1): useEffect polling + estado de conteo.
 * Tuteo limeño culto. D3.1: solo accent terracotta. D3.2: LIGHT MODE.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { API_URL } from "@/lib/config";
import { getToken } from "@/lib/auth";

const POLL_INTERVAL_MS = 30_000;

export function InvitationsBadge() {
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
        const res = await fetch(`${API_URL}/api/projects/invitations/unread-count`, {
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
        // Network error — keep previous count, don't reset badge
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
      href="/invitations"
      className="inline-flex items-center gap-1.5 rounded-full bg-accent px-2.5 py-0.5 text-xs font-medium text-paper hover:opacity-90"
      title={`${count} invitación${count === 1 ? "" : "es"} pendiente${count === 1 ? "" : "s"}`}
    >
      <span>{count}</span>
      <span>{count === 1 ? "invitación" : "invitaciones"}</span>
    </Link>
  );
}
