/**
 * Página /settings/rules — gestión de reglas persistentes del user.
 *
 * Las rules se inyectan en el system_prompt de cada chat según su scope
 * (global / project / use_case). El user puede crear, activar/desactivar
 * y borrar.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import type { Project } from "@/lib/user";

type Rule = {
  id: number;
  user_id: number;
  project_id: number | null;
  use_case_id: number | null;
  content: string;
  active: boolean;
  scope: "global" | "project" | "use_case";
  created_at: string;
};

export default function RulesPage() {
  const router = useRouter();
  const [rules, setRules] = useState<Rule[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [scopeMode, setScopeMode] = useState<"global" | "project" | "use_case">("global");
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [selectedUseCaseId, setSelectedUseCaseId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      try {
        const [rRes, pRes] = await Promise.all([
          fetch(`${API_URL}/rules`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${API_URL}/projects`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ]);
        if (rRes.status === 401) {
          clearToken();
          router.replace("/?error=session_expired");
          return;
        }
        if (!rRes.ok) throw new Error(`/rules HTTP ${rRes.status}`);
        if (!pRes.ok) throw new Error(`/projects HTTP ${pRes.status}`);
        setRules(await rRes.json());
        setProjects(await pRes.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error desconocido");
      }
    })();
  }, [router]);

  async function handleCreate() {
    if (!content.trim() || saving) return;
    const token = getToken();
    if (!token) return;

    const body: {
      content: string;
      project_id?: number;
      use_case_id?: number;
    } = { content: content.trim() };
    if (scopeMode === "project" && selectedProjectId) {
      body.project_id = selectedProjectId;
    }
    if (scopeMode === "use_case" && selectedProjectId && selectedUseCaseId) {
      body.project_id = selectedProjectId;
      body.use_case_id = selectedUseCaseId;
    }

    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/rules`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const newRule: Rule = await res.json();
      setRules((prev) => [newRule, ...prev]);
      setContent("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error creando regla");
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(rule: Rule) {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/rules/${rule.id}`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ active: !rule.active }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated: Rule = await res.json();
      setRules((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error actualizando");
    }
  }

  async function handleDelete(ruleId: number) {
    if (!confirm("¿Borrar esta regla?")) return;
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/rules/${ruleId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error borrando");
    }
  }

  const selectedProject = projects.find((p) => p.id === selectedProjectId) ?? null;

  return (
    <main className="flex-1 overflow-y-auto px-6 py-12">
      <div className="mx-auto w-full max-w-3xl">
        <header className="mb-10 flex items-end justify-between border-b border-rule pb-6">
          <div>
            <p className="font-serif text-2xl italic tracking-tight text-ink">
              Anoven
            </p>
            <h1 className="mt-4 font-serif text-4xl font-medium tracking-tight text-ink">
              Reglas
            </h1>
            <p className="mt-2 text-sm text-ink-soft">
              Instrucciones persistentes que los mentores respetan en cada
              chat. Pueden ser globales, por project o por use_case.
            </p>
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

        {/* Form de creación */}
        <div className="mb-10 rounded-xl border border-rule bg-paper-dim p-5">
          <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
            Nueva regla
          </p>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder='Ej: "Respondeme siempre en voseo rioplatense" o "Mi presupuesto es $50/mes, no recomiendes herramientas más caras"'
            rows={3}
            className="mt-3 w-full resize-none rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-muted outline-none focus:border-accent"
          />

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="text-xs text-ink-muted">Scope:</span>
            {(["global", "project", "use_case"] as const).map((s) => (
              <label key={s} className="flex items-center gap-1.5 text-sm text-ink-soft">
                <input
                  type="radio"
                  checked={scopeMode === s}
                  onChange={() => setScopeMode(s)}
                  className="accent-accent"
                />
                {s === "global" ? "Global" : s === "project" ? "Project" : "Use case"}
              </label>
            ))}
          </div>

          {scopeMode !== "global" && (
            <div className="mt-3 flex flex-wrap gap-3">
              <select
                value={selectedProjectId ?? ""}
                onChange={(e) => {
                  setSelectedProjectId(e.target.value ? Number(e.target.value) : null);
                  setSelectedUseCaseId(null);
                }}
                className="rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink"
              >
                <option value="">Elegí project</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>

              {scopeMode === "use_case" && selectedProject && (
                <select
                  value={selectedUseCaseId ?? ""}
                  onChange={(e) =>
                    setSelectedUseCaseId(e.target.value ? Number(e.target.value) : null)
                  }
                  className="rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink"
                >
                  <option value="">Elegí use case</option>
                  {selectedProject.use_cases.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          <button
            onClick={handleCreate}
            disabled={saving || !content.trim() || (scopeMode === "project" && !selectedProjectId) || (scopeMode === "use_case" && (!selectedProjectId || !selectedUseCaseId))}
            className="mt-4 rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-50"
          >
            {saving ? "Guardando..." : "Crear regla"}
          </button>
        </div>

        {/* Lista */}
        <p className="mb-3 text-[11px] uppercase tracking-[0.14em] text-ink-muted">
          {rules.length} regla{rules.length === 1 ? "" : "s"}
        </p>
        {rules.length === 0 && (
          <p className="rounded-xl border border-rule bg-paper-dim p-6 text-center font-serif italic text-ink-soft">
            Todavía no tenés reglas. Creá la primera arriba.
          </p>
        )}

        <ul className="space-y-3">
          {rules.map((r) => (
            <li
              key={r.id}
              className={
                r.active
                  ? "rounded-xl border border-rule bg-paper-dim p-4"
                  : "rounded-xl border border-rule bg-paper p-4 opacity-60"
              }
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <span
                    className={
                      r.scope === "global"
                        ? "inline-block rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-accent"
                        : "inline-block rounded-full bg-paper-deep px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-ink-soft"
                    }
                  >
                    {r.scope}
                  </span>
                  <p className="mt-2 font-serif text-base leading-snug text-ink">
                    {r.content}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col gap-2">
                  <button
                    onClick={() => handleToggle(r)}
                    className="rounded-md border border-rule px-2.5 py-1 text-xs text-ink-soft hover:bg-paper hover:text-ink"
                  >
                    {r.active ? "Desactivar" : "Activar"}
                  </button>
                  <button
                    onClick={() => handleDelete(r.id)}
                    className="rounded-md border border-rule px-2.5 py-1 text-xs text-ink-soft hover:bg-accent-soft hover:text-accent"
                  >
                    Borrar
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
