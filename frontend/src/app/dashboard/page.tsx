/**
 * Dashboard — pantalla home post-login.
 *
 * Sidebar viene de AppShell. Acá solo el "main panel": welcome + mentor picker
 * + botón "+ Crear mentor". El user clickea un mentor → POST /conversations →
 * navega a /chat/{id}, donde el sidebar (mismo) se mantiene.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";

type Mentor = {
  id: number;
  slug: string;
  nombre: string;
  canon: string;
  filosofia: string;
};

type MyMentor = {
  mentor: Mentor;
  source: string;
  match_reason: string | null;
};

export default function DashboardPage() {
  const router = useRouter();
  const [mentors, setMentors] = useState<MyMentor[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState<number | null>(null);
  const [openingCreator, setOpeningCreator] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API_URL}/mentors/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.status === 401) {
          clearToken();
          router.replace("/?error=session_expired");
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setMentors(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error");
      }
    })();
  }, [router]);

  async function handleOpen(mentorId: number) {
    if (opening !== null) return;
    const token = getToken();
    if (!token) return;
    setOpening(mentorId);
    try {
      const res = await fetch(`${API_URL}/conversations`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ mentor_id: mentorId }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const conv = await res.json();
      router.push(`/chat/${conv.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
      setOpening(null);
    }
  }

  async function handleOpenCreator() {
    if (openingCreator) return;
    const token = getToken();
    if (!token) return;
    setOpeningCreator(true);
    try {
      const creatorRes = await fetch(`${API_URL}/mentors/creator`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!creatorRes.ok) throw new Error(`HTTP ${creatorRes.status}`);
      const creator = await creatorRes.json();
      const convRes = await fetch(`${API_URL}/conversations`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ mentor_id: creator.id }),
      });
      if (!convRes.ok) throw new Error(`HTTP ${convRes.status}`);
      const conv = await convRes.json();
      router.push(`/chat/${conv.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
      setOpeningCreator(false);
    }
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-6 py-12">
        <div className="mx-auto w-full max-w-4xl">
          <header className="mb-10 border-b border-rule pb-6">
            <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              Bienvenido
            </p>
            <h1 className="mt-2 font-serif text-4xl font-medium tracking-tight text-ink">
              Empezá una conversación
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-ink-soft">
              Elegí un mentor para charlar de algo concreto. La conversación
              queda guardada y la encontrás en el sidebar a la izquierda.
              Cambiando de project, las conversaciones se filtran al contexto
              de ese project.
            </p>
          </header>

          {error && (
            <p className="mb-6 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
              {error}
            </p>
          )}

          {mentors === null ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="h-56 animate-pulse-dot rounded-2xl border border-rule bg-paper-dim"
                />
              ))}
            </div>
          ) : mentors.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-rule bg-paper-dim p-10 text-center">
              <p className="font-serif text-xl italic text-ink-soft">
                Todavía no tenés mentores asignados.
              </p>
              <p className="mt-2 text-sm text-ink-muted">
                Después de la entrevista de onboarding, el MentorMatcher te
                arma tu equipo.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {mentors.map((m, i) => (
                <div
                  key={m.mentor.id}
                  className="animate-fade-in-up"
                  style={{ animationDelay: `${i * 40}ms` }}
                >
                  <MentorCard
                    item={m}
                    onOpen={handleOpen}
                    opening={opening === m.mentor.id}
                  />
                </div>
              ))}
            </div>
          )}

          <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div
              className="animate-fade-in-up flex flex-col rounded-2xl border border-dashed border-rule-strong bg-paper-dim p-6 text-center"
              style={{ animationDelay: "300ms" }}
            >
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                Explorá más mentores
              </p>
              <p className="mt-2 font-serif text-xl italic text-ink">
                Sumá del catálogo
              </p>
              <p className="mx-auto mt-2 max-w-md text-sm text-ink-soft">
                Hay otros mentores listos para sumarse a tu equipo. Mirá el
                catálogo, agregá los que te sirvan, sacá los que no.
              </p>
              <Link
                href="/mentors"
                className="mx-auto mt-4 inline-flex rounded-xl border border-rule bg-paper px-5 py-2.5 text-sm font-medium text-ink transition-colors hover:border-accent hover:text-accent"
              >
                Ver mentores →
              </Link>
            </div>
            <div
              className="animate-fade-in-up flex flex-col rounded-2xl border border-dashed border-rule-strong bg-paper-dim p-6 text-center"
              style={{ animationDelay: "360ms" }}
            >
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                ¿Falta un mentor?
              </p>
              <p className="mt-2 font-serif text-xl italic text-ink">
                Creá tu propio mentor a medida
              </p>
              <p className="mx-auto mt-2 max-w-md text-sm text-ink-soft">
                El Creador te entrevista para entender qué oficio, canon y voz
                necesitás. Después arma el mentor y queda en tu equipo.
              </p>
              <button
                onClick={handleOpenCreator}
                disabled={openingCreator}
                className="mx-auto mt-4 rounded-xl bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-hover disabled:opacity-60"
              >
                {openingCreator ? "Abriendo..." : "+ Crear mentor"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function MentorCard({
  item,
  onOpen,
  opening,
}: {
  item: MyMentor;
  onOpen: (mentorId: number) => void;
  opening: boolean;
}) {
  const { mentor, source, match_reason } = item;
  const isMatched = source === "matched";

  return (
    <article className="shadow-card hover:shadow-card-hover flex h-full flex-col rounded-2xl border border-rule bg-paper-dim p-5 transition-all hover:-translate-y-0.5 hover:border-rule-strong">
      <div className="flex items-start justify-between gap-2">
        <h2 className="font-serif text-xl font-medium tracking-tight text-ink">
          {mentor.nombre}
        </h2>
        {isMatched && (
          <span className="shrink-0 rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-accent">
            Matched
          </span>
        )}
      </div>
      <p className="mt-1.5 text-[10px] uppercase tracking-[0.14em] text-ink-muted line-clamp-1">
        {mentor.canon}
      </p>
      <p className="mt-3 font-serif text-sm italic leading-relaxed text-ink-soft line-clamp-3">
        {mentor.filosofia}
      </p>
      {match_reason && (
        <p className="mt-3 border-t border-rule pt-2 text-xs leading-5 text-ink line-clamp-3">
          {match_reason}
        </p>
      )}
      <button
        onClick={() => onOpen(mentor.id)}
        disabled={opening}
        className="mt-4 w-full rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-hover disabled:opacity-60"
      >
        {opening ? "Abriendo..." : "Hablar"}
      </button>
    </article>
  );
}
