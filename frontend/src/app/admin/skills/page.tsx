/**
 * /admin/skills — CRUD de skills de mentores.
 *
 * Permite listar, crear, editar, togglear enabled, y eliminar skills.
 * Solo accesible para role='admin'. Redirige a /dashboard si el JWT no
 * tiene permisos (API devuelve 403).
 *
 * Parte del ciclo mentor-tools-system / Fase 1.5.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Skill = {
  id: number;
  mentor_id: number;
  mentor_nombre: string;
  mentor_slug: string;
  slug: string;
  title: string;
  content: string;
  triggers: string[] | null;
  enabled: boolean;
  position: number;
  created_at: string;
  updated_at: string;
};

type MentorOption = {
  id: number;
  slug: string;
  nombre: string;
};

type FormState = {
  mentor_id: number | "";
  slug: string;
  title: string;
  content: string;
  triggers: string;
  enabled: boolean;
};

const EMPTY_FORM: FormState = {
  mentor_id: "",
  slug: "",
  title: "",
  content: "",
  triggers: "",
  enabled: true,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } : {};
}

async function apiFetch(path: string, opts?: RequestInit) {
  return fetch(`${API_URL}${path}`, {
    ...opts,
    headers: { ...authHeaders(), ...(opts?.headers ?? {}) },
  });
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminSkillsPage() {
  const router = useRouter();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [mentors, setMentors] = useState<MentorOption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Form state — null = hidden, id = editing, -1 = creating new
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);

  // Delete confirmation
  const [deletingId, setDeletingId] = useState<number | null>(null);

  // ---------------------------------------------------------------------------
  // Load data
  // ---------------------------------------------------------------------------

  async function loadAll() {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    try {
      const [skillsRes, mentorsRes] = await Promise.all([
        apiFetch("/api/admin/skills"),
        apiFetch("/api/admin/mentors-list"),
      ]);

      if (skillsRes.status === 401 || mentorsRes.status === 401) {
        clearToken();
        router.replace("/?error=session_expired");
        return;
      }
      if (skillsRes.status === 403 || mentorsRes.status === 403) {
        router.replace("/dashboard?error=admin_only");
        return;
      }
      if (!skillsRes.ok) throw new Error(`HTTP ${skillsRes.status}`);
      if (!mentorsRes.ok) throw new Error(`HTTP ${mentorsRes.status}`);

      setSkills(await skillsRes.json());
      setMentors(await mentorsRes.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error cargando skills");
    }
  }

  useEffect(() => {
    loadAll();
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------------------
  // Form helpers
  // ---------------------------------------------------------------------------

  function openCreate() {
    setEditingId(-1);
    setForm(EMPTY_FORM);
    setFormError(null);
  }

  function openEdit(skill: Skill) {
    setEditingId(skill.id);
    setForm({
      mentor_id: skill.mentor_id,
      slug: skill.slug,
      title: skill.title,
      content: skill.content,
      triggers: skill.triggers ? skill.triggers.join(", ") : "",
      enabled: skill.enabled,
    });
    setFormError(null);
  }

  function closeForm() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
  }

  function parseTriggersField(raw: string): string[] | null {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    return trimmed.split(",").map((t) => t.trim()).filter(Boolean);
  }

  // ---------------------------------------------------------------------------
  // CRUD actions
  // ---------------------------------------------------------------------------

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setFormError(null);

    if (!form.title.trim()) {
      setFormError("El titulo no puede estar vacio.");
      return;
    }
    if (!form.content.trim()) {
      setFormError("El contenido no puede estar vacio.");
      return;
    }
    if (!form.slug.trim()) {
      setFormError("El slug no puede estar vacio.");
      return;
    }
    if (form.mentor_id === "") {
      setFormError("Selecciona un mentor.");
      return;
    }

    setBusy(true);
    const payload = {
      mentor_id: form.mentor_id,
      slug: form.slug.trim(),
      title: form.title.trim(),
      content: form.content,
      triggers: parseTriggersField(form.triggers),
      enabled: form.enabled,
    };

    try {
      let res: Response;
      if (editingId === -1) {
        // Create
        res = await apiFetch("/api/admin/skills", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      } else {
        // Update (PUT — send all fields)
        res = await apiFetch(`/api/admin/skills/${editingId}`, {
          method: "PUT",
          body: JSON.stringify({
            title: payload.title,
            content: payload.content,
            triggers: payload.triggers,
            enabled: payload.enabled,
            // slug is immutable after creation
          }),
        });
      }

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail = body?.detail ?? `HTTP ${res.status}`;
        setFormError(typeof detail === "string" ? detail : JSON.stringify(detail));
        return;
      }

      closeForm();
      await loadAll();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Error guardando");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleEnabled(skill: Skill) {
    if (busy) return;
    setBusy(true);
    try {
      const res = await apiFetch(`/api/admin/skills/${skill.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !skill.enabled }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSkills((prev) =>
        prev.map((s) => (s.id === skill.id ? { ...s, enabled: !s.enabled } : s))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error toggling");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(id: number) {
    if (busy) return;
    setBusy(true);
    try {
      const res = await apiFetch(`/api/admin/skills/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSkills((prev) => prev.filter((s) => s.id !== id));
      setDeletingId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error eliminando");
    } finally {
      setBusy(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <main className="flex-1 overflow-y-auto px-6 py-12">
      <div className="mx-auto w-full max-w-5xl">

        {/* Header */}
        <header className="mb-10 flex items-end justify-between border-b border-rule pb-6">
          <div>
            <p className="font-serif text-2xl italic tracking-tight text-ink">
              Anoven · Admin
            </p>
            <h1 className="mt-4 font-serif text-4xl font-medium tracking-tight text-ink">
              Skills
            </h1>
            <p className="mt-2 text-sm text-ink-soft">
              {skills.length} skill{skills.length !== 1 ? "s" : ""} en la base.
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Link
              href="/admin"
              className="text-sm text-ink-soft underline-offset-4 hover:text-accent hover:underline"
            >
              ← Panel
            </Link>
            <Link
              href="/dashboard"
              className="text-xs text-ink-soft underline-offset-2 hover:text-accent hover:underline"
            >
              Dashboard →
            </Link>
          </div>
        </header>

        {/* Error banner */}
        {error && (
          <div className="mb-6 rounded-lg border border-accent bg-accent-soft px-4 py-3 text-sm text-accent">
            {error}
            <button
              onClick={() => setError(null)}
              className="ml-4 text-xs underline opacity-70 hover:opacity-100"
            >
              cerrar
            </button>
          </div>
        )}

        {/* Create button */}
        {editingId === null && (
          <div className="mb-6">
            <button
              onClick={openCreate}
              className="rounded-lg border border-accent bg-accent px-4 py-2 text-sm font-medium text-paper hover:opacity-90"
            >
              + Nueva skill
            </button>
          </div>
        )}

        {/* Form: create or edit */}
        {editingId !== null && (
          <section className="mb-8 rounded-xl border border-rule bg-paper-dim p-6">
            <h2 className="mb-4 font-serif text-2xl italic text-ink">
              {editingId === -1 ? "Nueva skill" : "Editar skill"}
            </h2>

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Mentor selector — only for create; immutable after */}
              {editingId === -1 && (
                <div>
                  <label className="block text-xs uppercase tracking-[0.12em] text-ink-muted mb-1">
                    Mentor
                  </label>
                  <select
                    className="w-full rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
                    value={form.mentor_id}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        mentor_id: e.target.value === "" ? "" : Number(e.target.value),
                      }))
                    }
                    required
                  >
                    <option value="">Seleccioná un mentor...</option>
                    {mentors.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.nombre} ({m.slug})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Slug — immutable after create */}
              <div>
                <label className="block text-xs uppercase tracking-[0.12em] text-ink-muted mb-1">
                  Slug{editingId !== -1 && <span className="ml-1 text-ink-muted">(inmutable)</span>}
                </label>
                {editingId === -1 ? (
                  <input
                    type="text"
                    className="w-full rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none font-mono"
                    placeholder="ej: atomic-design"
                    value={form.slug}
                    onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
                    required
                  />
                ) : (
                  <p className="rounded-lg border border-rule bg-paper px-3 py-2 text-sm font-mono text-ink-soft">
                    {form.slug}
                  </p>
                )}
              </div>

              {/* Title */}
              <div>
                <label className="block text-xs uppercase tracking-[0.12em] text-ink-muted mb-1">
                  Titulo
                </label>
                <input
                  type="text"
                  className="w-full rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
                  placeholder="ej: Atomic Design System"
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                  required
                />
              </div>

              {/* Content */}
              <div>
                <label className="block text-xs uppercase tracking-[0.12em] text-ink-muted mb-1">
                  Contenido (Markdown)
                </label>
                <textarea
                  className="w-full rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none font-mono min-h-[200px] resize-y"
                  placeholder="## Cuerpo de la skill en markdown..."
                  value={form.content}
                  onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
                  required
                />
              </div>

              {/* Triggers */}
              <div>
                <label className="block text-xs uppercase tracking-[0.12em] text-ink-muted mb-1">
                  Triggers (coma-separados, opcional)
                </label>
                <input
                  type="text"
                  className="w-full rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
                  placeholder="ej: react, componentes, ui"
                  value={form.triggers}
                  onChange={(e) => setForm((f) => ({ ...f, triggers: e.target.value }))}
                />
              </div>

              {/* Enabled toggle */}
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="enabled"
                  checked={form.enabled}
                  onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
                  className="h-4 w-4 accent-accent"
                />
                <label htmlFor="enabled" className="text-sm text-ink">
                  Habilitada
                </label>
              </div>

              {/* Form error */}
              {formError && (
                <p className="rounded-lg border border-accent bg-accent-soft px-3 py-2 text-sm text-accent">
                  {formError}
                </p>
              )}

              {/* Actions */}
              <div className="flex gap-3 pt-2">
                <button
                  type="submit"
                  disabled={busy}
                  className="rounded-lg border border-accent bg-accent px-4 py-2 text-sm font-medium text-paper hover:opacity-90 disabled:opacity-50"
                >
                  {busy ? "Guardando..." : editingId === -1 ? "Crear skill" : "Guardar cambios"}
                </button>
                <button
                  type="button"
                  onClick={closeForm}
                  className="rounded-lg border border-rule px-4 py-2 text-sm text-ink-soft hover:text-ink"
                >
                  Cancelar
                </button>
              </div>
            </form>
          </section>
        )}

        {/* Skills table */}
        <div className="overflow-x-auto rounded-xl border border-rule bg-paper-dim">
          <table className="w-full text-sm">
            <thead className="border-b border-rule text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              <tr>
                <th className="px-4 py-3 text-left">Skill</th>
                <th className="px-4 py-3 text-left">Mentor</th>
                <th className="px-4 py-3 text-center">Pos</th>
                <th className="px-4 py-3 text-center">Estado</th>
                <th className="px-4 py-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {skills.map((skill) => (
                <tr key={skill.id} className="border-b border-rule last:border-b-0">
                  <td className="px-4 py-3">
                    <p className="font-serif text-base italic text-ink">{skill.title}</p>
                    <p className="font-mono text-[11px] text-ink-muted">{skill.slug}</p>
                  </td>
                  <td className="px-4 py-3">
                    <p className="text-sm text-ink">{skill.mentor_nombre}</p>
                    <p className="text-[11px] text-ink-muted">{skill.mentor_slug}</p>
                  </td>
                  <td className="px-4 py-3 text-center tabular-nums text-xs text-ink-muted">
                    {skill.position}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => handleToggleEnabled(skill)}
                      disabled={busy}
                      title={skill.enabled ? "Deshabilitar" : "Habilitar"}
                      className="inline-flex items-center gap-1 text-xs disabled:opacity-40"
                    >
                      {skill.enabled ? (
                        <span className="rounded-full bg-leaf-soft px-2 py-0.5 text-[10px] uppercase tracking-wide text-leaf">
                          activa
                        </span>
                      ) : (
                        <span className="rounded-full bg-paper px-2 py-0.5 text-[10px] uppercase tracking-wide text-ink-muted border border-rule">
                          inactiva
                        </span>
                      )}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-3">
                      <button
                        onClick={() => openEdit(skill)}
                        disabled={busy || editingId !== null}
                        className="text-xs text-ink-soft underline-offset-2 hover:text-accent hover:underline disabled:opacity-40"
                      >
                        Editar
                      </button>
                      {deletingId === skill.id ? (
                        <span className="flex items-center gap-2">
                          <button
                            onClick={() => handleDelete(skill.id)}
                            disabled={busy}
                            className="text-xs font-medium text-accent hover:underline disabled:opacity-40"
                          >
                            Confirmar
                          </button>
                          <button
                            onClick={() => setDeletingId(null)}
                            className="text-xs text-ink-muted hover:text-ink"
                          >
                            Cancelar
                          </button>
                        </span>
                      ) : (
                        <button
                          onClick={() => setDeletingId(skill.id)}
                          disabled={busy || editingId !== null}
                          className="text-xs text-ink-muted underline-offset-2 hover:text-accent hover:underline disabled:opacity-40"
                        >
                          Eliminar
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {skills.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center font-serif italic text-ink-soft">
                    No hay skills todavia. Crea la primera.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Footer info */}
        <p className="mt-6 text-[11px] text-ink-muted">
          Las skills se inyectan en el system_prompt en el proximo turno de conversacion.
          El cache se invalida en hasta 60 segundos tras un cambio.
        </p>
      </div>
    </main>
  );
}
