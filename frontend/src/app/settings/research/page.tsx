/**
 * Página /settings/research — toggle de opt-in para uso de conversaciones
 * en investigación de producto (anonimizadas).
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import type { User } from "@/lib/user";

export default function ResearchSettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API_URL}/users/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.status === 401) {
          clearToken();
          router.replace("/");
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setUser(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error");
      }
    })();
  }, [router]);

  async function handleToggle(next: boolean) {
    if (!user || saving) return;
    const token = getToken();
    if (!token) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/users/me/research-opt-in`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ research_opt_in: next }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setUser(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="flex-1 overflow-y-auto px-6 py-12">
      <div className="mx-auto w-full max-w-2xl">
        <header className="mb-10 flex items-end justify-between border-b border-rule pb-6">
          <div>
            <p className="font-serif text-2xl italic tracking-tight text-ink">
              Anoven
            </p>
            <h1 className="mt-4 font-serif text-4xl font-medium tracking-tight text-ink">
              Investigación
            </h1>
          </div>
          <Link
            href="/dashboard"
            className="text-sm text-ink-soft underline-offset-4 hover:text-accent hover:underline"
          >
            ← Dashboard
          </Link>
        </header>

        {error && (
          <p className="mb-6 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
            {error}
          </p>
        )}

        <div className="rounded-xl border border-rule bg-paper-dim p-6">
          <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
            Uso de tus conversaciones para mejorar Anoven
          </p>
          <p className="mt-3 font-serif text-lg italic leading-relaxed text-ink">
            ¿Podemos usar tus conversaciones con los mentores —
            anonimizadas y agregadas— para mejorar el producto, los prompts
            de los mentores, y entender cómo la gente usa la IA?
          </p>
          <ul className="mt-4 space-y-1.5 text-sm text-ink-soft">
            <li>· Tus datos quedan anonimizados.</li>
            <li>· Anoven NO los vende ni los comparte con terceros.</li>
            <li>· Podés cambiar tu decisión en cualquier momento.</li>
          </ul>

          <div className="mt-6 flex items-center gap-3">
            <button
              onClick={() => handleToggle(!user?.research_opt_in)}
              disabled={saving || !user}
              className={
                user?.research_opt_in
                  ? "rounded-full bg-accent px-5 py-2 text-sm font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-60"
                  : "rounded-full border border-rule-strong bg-paper px-5 py-2 text-sm font-medium text-ink hover:bg-paper-deep disabled:opacity-60"
              }
            >
              {saving
                ? "Guardando..."
                : user?.research_opt_in
                ? "✓ Aceptado — desactivar"
                : "Acepto que usen mis charlas (anonimizadas)"}
            </button>
            <span className="text-xs text-ink-muted">
              Estado actual:{" "}
              {user?.research_opt_in ? (
                <span className="text-accent">opt-in</span>
              ) : (
                <span>opt-out</span>
              )}
            </span>
          </div>
        </div>
      </div>
    </main>
  );
}
