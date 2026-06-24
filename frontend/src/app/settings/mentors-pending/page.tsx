/**
 * /settings/mentors-pending — FASE 7.
 *
 * Lista de `MentorRequest` con status='pending' del user. Son mentores que
 * el Evaluador detectó como dolor del user pero NO existen todavía en el
 * catálogo. El user puede armarlos hablando con el Creador.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";

type PendingMentor = {
  id: number;
  proposed_name: string;
  proposed_canon: string | null;
  why: string;
  source: string;
  created_at: string | null;
};

export default function PendingMentorsPage() {
  const router = useRouter();
  const [pendings, setPendings] = useState<PendingMentor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API_URL}/users/me/pending-mentors`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.status === 401) {
          clearToken();
          router.replace("/");
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setPendings(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error");
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  async function handleAskCreator(pending: PendingMentor) {
    // Abrir un chat con el Creador, prellenando un mensaje con el contexto
    // del pending. El Creador toma esa info para empezar a armar el mentor.
    const token = getToken();
    if (!token) return;

    const initialMessage =
      `Quiero armar un mentor para: ${pending.proposed_name}.\n\n` +
      `Por qué lo necesito: ${pending.why}` +
      (pending.proposed_canon
        ? `\n\nEl evaluador propuso este canon inicial: ${pending.proposed_canon}`
        : "");

    try {
      // Buscar o crear conversación con el Creador
      const res = await fetch(`${API_URL}/conversations`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          mentor_slug: "anoven-creador",
          first_message: initialMessage,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const conv = await res.json();
      router.push(`/chat/${conv.id}`);
    } catch (err) {
      setError(
        err instanceof Error
          ? `Error al abrir chat con Creador: ${err.message}`
          : "Error",
      );
    }
  }

  return (
    <AppShell>
      <main className="flex-1 overflow-y-auto px-6 py-12">
        <div className="mx-auto w-full max-w-3xl">
          <header className="mb-10 flex items-end justify-between border-b border-rule pb-6">
            <div>
              <p className="font-serif text-2xl italic tracking-tight text-ink">
                Anoven
              </p>
              <h1 className="mt-4 font-serif text-4xl font-medium tracking-tight text-ink">
                Mentores sugeridos
              </h1>
              <p className="mt-2 text-sm text-ink-soft">
                Mentores que el Evaluador detectó como interés tuyo pero que
                todavía no existen en Anoven. Podés armarlos hablando con el
                Creador.
              </p>
            </div>
            <Link
              href="/settings"
              className="text-sm text-ink-soft underline-offset-4 hover:text-accent hover:underline"
            >
              ← Configuración
            </Link>
          </header>

          {error && (
            <p className="mb-6 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-center font-serif italic text-ink-muted">
              Cargando...
            </p>
          )}

          {!loading && pendings.length === 0 && (
            <div className="rounded-xl border border-rule bg-paper-dim p-8 text-center">
              <p className="font-serif text-xl italic text-ink-soft">
                Sin mentores pendientes
              </p>
              <p className="mt-3 text-sm text-ink-muted">
                Cuando el Evaluador detecte gustos tuyos que no estén
                cubiertos por el catálogo actual, aparecerán acá. También
                podés pedirle uno al Creador directamente desde el chat.
              </p>
              <Link
                href="/chat/new?mentor=anoven-creador"
                className="mt-5 inline-flex rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-ink hover:bg-accent-hover"
              >
                Hablar con el Creador →
              </Link>
            </div>
          )}

          {!loading && pendings.length > 0 && (
            <ul className="space-y-3">
              {pendings.map((p) => (
                <li
                  key={p.id}
                  className="animate-fade-in-up rounded-xl border border-rule bg-paper-dim p-5"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <span className="inline-block rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-accent">
                        {p.source === "interview" ? "De entrevista" : "Manual"}
                      </span>
                      <h3 className="mt-2 font-serif text-2xl italic text-ink">
                        {p.proposed_name}
                      </h3>
                      <p className="mt-2 text-sm leading-relaxed text-ink-soft">
                        {p.why}
                      </p>
                      {p.proposed_canon && (
                        <p className="mt-3 text-xs text-ink-muted">
                          <span className="uppercase tracking-[0.12em]">
                            Canon propuesto:
                          </span>{" "}
                          {p.proposed_canon}
                        </p>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => handleAskCreator(p)}
                    className="mt-4 inline-flex rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-ink hover:bg-accent-hover"
                  >
                    Pedirle al Creador que lo arme →
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
    </AppShell>
  );
}
