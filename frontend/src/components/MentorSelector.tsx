/**
 * MentorSelector — lista de mentores globales con toggle para asignar al proyecto.
 *
 * "use client" justificado (A2.1): estado de selección multi-toggle + fetches async.
 * Tuteo limeño culto. D3.1: solo accent terracotta. D3.2: LIGHT MODE.
 */

"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/config";
import { getToken } from "@/lib/auth";

interface CatalogMentor {
  id: number;
  slug: string;
  nombre: string;
  canon: string;
  filosofia: string;
}

interface ProjectMentorRead {
  id: number;
  project_id: number;
  mentor_id: number;
  mentor_slug: string;
  mentor_nombre: string;
  added_by_user_email: string;
  added_at: string;
}

interface MentorSelectorProps {
  projectId: number;
  currentMentors: ProjectMentorRead[];
  isOwner: boolean;
  onChange: () => void;
}

export function MentorSelector({
  projectId,
  currentMentors,
  isOwner,
  onChange,
}: MentorSelectorProps) {
  const [catalog, setCatalog] = useState<CatalogMentor[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [toggling, setToggling] = useState<number | null>(null); // mentor_id being toggled
  const [toggleError, setToggleError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    fetch(`${API_URL}/mentors/catalog`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: CatalogMentor[]) => setCatalog(data))
      .catch((err) =>
        setLoadError(err instanceof Error ? err.message : "Error al cargar mentores"),
      );
  }, []);

  const assignedMentorIds = new Set(currentMentors.map((m) => m.mentor_id));

  async function handleToggle(mentor: CatalogMentor) {
    if (!isOwner) return;
    const token = getToken();
    if (!token) return;

    const isAssigned = assignedMentorIds.has(mentor.id);
    setToggling(mentor.id);
    setToggleError(null);

    try {
      if (isAssigned) {
        // Remove
        const res = await fetch(
          `${API_URL}/api/projects/${projectId}/mentors/${mentor.id}`,
          {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` },
          },
        );
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail ?? `HTTP ${res.status}`);
        }
      } else {
        // Add
        const res = await fetch(`${API_URL}/api/projects/${projectId}/mentors`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ mentor_id: mentor.id }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail ?? `HTTP ${res.status}`);
        }
      }
      onChange();
    } catch (err) {
      setToggleError(err instanceof Error ? err.message : "Error al actualizar el mentor");
    } finally {
      setToggling(null);
    }
  }

  if (loadError) {
    return (
      <div className="rounded-lg border border-accent bg-accent-soft px-4 py-3">
        <p className="text-sm text-accent">{loadError}</p>
      </div>
    );
  }

  if (catalog === null) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-14 animate-pulse rounded-xl border border-rule bg-paper-dim"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Assigned count header */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-soft">
          {assignedMentorIds.size}{" "}
          {assignedMentorIds.size === 1 ? "mentor asignado" : "mentores asignados"}
          {" "}de {catalog.length} disponibles.
        </p>
        {!isOwner && (
          <span className="text-xs text-ink-muted">
            Solo el propietario puede modificar los mentores.
          </span>
        )}
      </div>

      {/* Toggle error */}
      {toggleError && (
        <div className="rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
          {toggleError}
        </div>
      )}

      {/* Mentor list */}
      {catalog.map((mentor) => {
        const isAssigned = assignedMentorIds.has(mentor.id);
        const isProcessing = toggling === mentor.id;

        return (
          <div
            key={mentor.id}
            className={`flex items-center gap-3 rounded-xl border px-4 py-3 transition-colors ${
              isAssigned ? "border-accent bg-accent-soft/30" : "border-rule bg-paper-dim"
            }`}
          >
            {/* Toggle */}
            <button
              onClick={() => handleToggle(mentor)}
              disabled={!isOwner || isProcessing}
              aria-label={
                isAssigned
                  ? `Quitar ${mentor.nombre} del proyecto`
                  : `Agregar ${mentor.nombre} al proyecto`
              }
              className={`relative h-5 w-9 shrink-0 rounded-full transition-colors disabled:opacity-60 ${
                isAssigned ? "bg-accent" : "bg-rule"
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-paper shadow transition-transform ${
                  isAssigned ? "translate-x-4" : "translate-x-0"
                }`}
              />
              {isProcessing && (
                <span className="absolute inset-0 animate-pulse rounded-full bg-ink/10" />
              )}
            </button>

            {/* Mentor info */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-ink">{mentor.nombre}</p>
              <p className="text-xs text-ink-muted truncate">{mentor.canon}</p>
            </div>

            {isAssigned && (
              <span className="shrink-0 rounded-full bg-accent-soft px-2 py-0.5 text-[9px] font-medium uppercase tracking-wide text-accent">
                Asignado
              </span>
            )}
          </div>
        );
      })}

      {catalog.length === 0 && (
        <div className="rounded-2xl border border-dashed border-rule bg-paper-dim p-8 text-center">
          <p className="font-serif text-lg italic text-ink-soft">
            No hay mentores disponibles en el catálogo.
          </p>
        </div>
      )}
    </div>
  );
}
