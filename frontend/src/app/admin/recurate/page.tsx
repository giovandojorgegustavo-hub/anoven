/**
 * /admin/recurate — Panel de RECURACIÓN con Promptifex SDD.
 *
 * Lista los mentores globales con su estado de curación. Permite disparar
 * una pasada de Promptifex SDD por mentor, que:
 *   - Comprime el system_prompt al ~50-70% del tamaño
 *   - Genera una eval suite (4-6 evals medibles)
 *   - Bumpea la version del mentor (initial_seed v1 → promptifex_sdd v2)
 *
 * Distinto de /admin/curation (que es para aprobar custom mentors).
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";

type CurationStatus = {
  id: number;
  slug: string;
  nombre: string;
  version: number;
  curator: string | null;
  curated_at: string | null;
  eval_suite_topic_key: string | null;
  system_prompt_bytes: number;
  visibility: string;
  status: string;
};

type CurationResult = {
  mentor_id: number;
  slug: string;
  old_version: number;
  new_version: number;
  old_bytes: number;
  new_bytes: number;
  compression_ratio: number;
  change_summary: string;
  eval_count: number;
  eval_suite_topic_key: string;
};

function fmtBytes(n: number): string {
  if (n < 1024) return `${n}B`;
  return `${(n / 1024).toFixed(1)}KB`;
}

export default function AdminRecuratePage() {
  const router = useRouter();
  const [mentors, setMentors] = useState<CurationStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [curatingId, setCuratingId] = useState<number | null>(null);
  const [lastResult, setLastResult] = useState<CurationResult | null>(null);

  async function loadList() {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    try {
      const res = await fetch(`${API_URL}/api/admin/mentors/curation`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) {
        clearToken();
        router.replace("/");
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setMentors(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error cargando lista");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadList();
  }, []);

  async function handleCurate(mentor: CurationStatus) {
    if (curatingId !== null) return;
    if (
      !confirm(
        `Disparar Promptifex SDD sobre "${mentor.slug}"?\n\n` +
          `Esto va a tardar 30-60 segundos. Se va a:\n` +
          `  • Generar un system_prompt comprimido (objetivo ~${Math.round(mentor.system_prompt_bytes * 0.6)} bytes)\n` +
          `  • Definir 4-6 evals\n` +
          `  • Bumpear version ${mentor.version} → ${mentor.version + 1}\n\n` +
          `Si Promptifex falla, NO se persiste nada.`,
      )
    )
      return;

    setCuratingId(mentor.id);
    setLastResult(null);
    setError(null);

    const token = getToken();
    if (!token) return;

    try {
      const res = await fetch(`${API_URL}/api/admin/mentors/${mentor.id}/curate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || `HTTP ${res.status}`);
      }
      const result: CurationResult = await res.json();
      setLastResult(result);
      // Refrescar lista
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error en curación");
    } finally {
      setCuratingId(null);
    }
  }

  const initialCount = mentors.filter((m) => m.curator === "initial_seed").length;
  const curatedCount = mentors.filter((m) => m.curator === "promptifex_sdd").length;

  return (
    <AppShell>
      <main className="flex-1 overflow-y-auto px-6 py-12">
        <div className="mx-auto w-full max-w-5xl">
          <header className="mb-6 flex items-end justify-between border-b border-rule pb-6">
            <div>
              <p className="font-serif text-2xl italic tracking-tight text-ink">
                Anoven · Admin
              </p>
              <h1 className="mt-4 font-serif text-4xl font-medium tracking-tight text-ink">
                Estado de curación de mentores
              </h1>
              <p className="mt-2 max-w-2xl text-sm text-ink-soft">
                Vista read-only del estado de cada mentor (versión + curator +
                eval suite). La curación real se hace via PMTX cycle desde
                Claude Code — el botón single-shot está deprecated.
              </p>
            </div>
            <Link
              href="/admin"
              className="text-sm text-ink-soft underline-offset-4 hover:text-accent hover:underline"
            >
              ← Panel admin
            </Link>
          </header>

          {/* Warning DEPRECATED single-shot */}
          <div className="mb-8 rounded-xl border border-accent bg-accent-soft p-5">
            <p className="text-[11px] uppercase tracking-[0.14em] text-accent font-medium">
              ⚠ Single-shot curation DEPRECATED desde 2026-06-07
            </p>
            <p className="mt-2 text-sm leading-relaxed text-ink">
              El botón "Curar con Promptifex" abajo está deshabilitado. El
              endpoint backend devuelve 410 Gone. Para curar un mentor, usá el{" "}
              <strong>PMTX cycle real</strong> desde Claude Code — son 8 fases
              con eval suite trazable, anti-sycophancy y §17 Eval Protocol.
            </p>
            <p className="mt-2 text-xs text-ink-soft">
              Procedimiento completo:{" "}
              <code className="bg-paper px-1.5 py-0.5 rounded">
                /opt/anoven-shared/PMTX-CYCLE-SOP.md
              </code>
            </p>
          </div>

          {/* KPIs */}
          <div className="mb-6 grid grid-cols-3 gap-3">
            <div className="rounded-xl border border-rule bg-paper-dim p-4">
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                Sin curar (initial_seed)
              </p>
              <p className="mt-1 font-serif text-3xl font-medium text-ink">
                {initialCount}
              </p>
            </div>
            <div className="rounded-xl border border-accent-soft bg-accent-soft p-4">
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                Curados (promptifex_sdd)
              </p>
              <p className="mt-1 font-serif text-3xl font-medium text-accent">
                {curatedCount}
              </p>
            </div>
            <div className="rounded-xl border border-rule bg-paper-dim p-4">
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                Total
              </p>
              <p className="mt-1 font-serif text-3xl font-medium text-ink">
                {mentors.length}
              </p>
            </div>
          </div>

          {error && (
            <p className="mb-6 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
              {error}
            </p>
          )}

          {lastResult && (
            <div className="mb-6 animate-fade-in-up rounded-xl border border-accent bg-accent-soft p-5">
              <p className="text-[11px] uppercase tracking-[0.14em] text-accent">
                Última curación
              </p>
              <h3 className="mt-2 font-serif text-2xl italic text-ink">
                {lastResult.slug} → v{lastResult.new_version}
              </h3>
              <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.12em] text-ink-muted">
                    Antes
                  </p>
                  <p className="font-mono text-ink">
                    {fmtBytes(lastResult.old_bytes)}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-[0.12em] text-ink-muted">
                    Ahora
                  </p>
                  <p className="font-mono font-medium text-accent">
                    {fmtBytes(lastResult.new_bytes)}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-[0.12em] text-ink-muted">
                    Ratio
                  </p>
                  <p className="font-mono font-medium text-accent">
                    {(lastResult.compression_ratio * 100).toFixed(0)}%
                  </p>
                </div>
              </div>
              <p className="mt-3 text-sm text-ink-soft">
                <span className="font-medium">{lastResult.eval_count} evals</span>{" "}
                definidos en{" "}
                <code className="text-xs">{lastResult.eval_suite_topic_key}</code>
              </p>
              <details className="mt-3">
                <summary className="cursor-pointer text-xs text-ink-soft hover:text-ink">
                  Ver change_summary
                </summary>
                <pre className="mt-2 whitespace-pre-wrap rounded-md bg-paper p-3 text-xs text-ink-soft">
                  {lastResult.change_summary}
                </pre>
              </details>
            </div>
          )}

          {loading && (
            <p className="text-center font-serif italic text-ink-muted">
              Cargando lista...
            </p>
          )}

          {!loading && (
            <ul className="space-y-2">
              {mentors.map((m) => (
                <li
                  key={m.id}
                  className={
                    m.curator === "promptifex_sdd"
                      ? "rounded-xl border border-accent-soft bg-paper-dim p-4"
                      : "rounded-xl border border-rule bg-paper-dim p-4"
                  }
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-serif text-lg text-ink">
                          {m.nombre}
                        </h3>
                        <code className="text-xs text-ink-muted">{m.slug}</code>
                        <span
                          className={
                            m.curator === "promptifex_sdd"
                              ? "rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-accent"
                              : "rounded-full bg-paper-deep px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-ink-soft"
                          }
                        >
                          v{m.version} · {m.curator || "—"}
                        </span>
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-xs text-ink-muted">
                        <span>{fmtBytes(m.system_prompt_bytes)}</span>
                        {m.curated_at && (
                          <span>
                            curado:{" "}
                            {new Date(m.curated_at).toLocaleDateString()}
                          </span>
                        )}
                        {m.eval_suite_topic_key && (
                          <span className="truncate font-mono">
                            {m.eval_suite_topic_key}
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      disabled={true}
                      title="DEPRECATED — usá PMTX cycle desde Claude Code. Ver /opt/anoven-shared/PMTX-CYCLE-SOP.md"
                      className="rounded-lg border border-rule px-4 py-2 text-sm text-ink-muted opacity-40 cursor-not-allowed line-through"
                    >
                      Curar (deprecated)
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
    </AppShell>
  );
}
