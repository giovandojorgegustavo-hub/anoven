/**
 * /mentors — hub del user para gestionar su equipo de mentores.
 *
 * Dos tabs:
 *   - "Mi equipo": mentores asignados al user (GET /mentors/me).
 *     Permite quitar cualquiera (DELETE /users/me/mentors/{id}). El backend
 *     soft-deletea — el user es dueño de su workspace, incluso los default.
 *   - "Catálogo": mentores globales activos que el user TODAVÍA no tiene
 *     (GET /mentors/catalog). Permite agregar (POST /users/me/mentors).
 *
 * Después de agregar/quitar, refresca ambas listas para mantener consistencia.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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

type CatalogMentor = {
  id: number;
  slug: string;
  nombre: string;
  canon: string;
  filosofia: string;
};

type Tab = "team" | "catalog";

// ---------------------------------------------------------------------------
// Source labels — mapa convención backend → etiqueta human
// ---------------------------------------------------------------------------

const SOURCE_LABELS: Record<string, { label: string; tone: "neutral" | "accent" | "ink" }> = {
  default: { label: "Default", tone: "neutral" },
  matched: { label: "Matched", tone: "accent" },
  created_by_self: { label: "Agregado por vos", tone: "ink" },
  assigned_by_admin: { label: "Asignado por admin", tone: "neutral" },
};

function sourceBadge(source: string) {
  const meta = SOURCE_LABELS[source] ?? { label: source, tone: "neutral" as const };
  const classes =
    meta.tone === "accent"
      ? "bg-accent-soft text-accent"
      : meta.tone === "ink"
        ? "bg-paper text-ink border border-rule"
        : "bg-paper text-ink-muted border border-rule";
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] ${classes}`}
    >
      {meta.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function MentorsPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("team");
  const [team, setTeam] = useState<MyMentor[] | null>(null);
  const [catalog, setCatalog] = useState<CatalogMentor[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    try {
      const [teamRes, catRes] = await Promise.all([
        fetch(`${API_URL}/mentors/me`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${API_URL}/mentors/catalog`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);
      if (teamRes.status === 401 || catRes.status === 401) {
        clearToken();
        router.replace("/?error=session_expired");
        return;
      }
      if (!teamRes.ok) throw new Error(`HTTP ${teamRes.status} on /mentors/me`);
      if (!catRes.ok) throw new Error(`HTTP ${catRes.status} on /mentors/catalog`);
      setTeam(await teamRes.json());
      setCatalog(await catRes.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    }
  }, [router]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  function showFlash(msg: string) {
    setFlash(msg);
    setTimeout(() => setFlash(null), 2400);
  }

  async function handleAdd(mentor: CatalogMentor) {
    if (pendingId !== null) return;
    const token = getToken();
    if (!token) return;
    setError(null);
    setPendingId(mentor.id);
    try {
      const res = await fetch(`${API_URL}/users/me/mentors`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ mentor_id: mentor.id }),
      });
      if (res.status === 409) {
        showFlash(`${mentor.nombre} ya está en tu equipo.`);
      } else if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      } else {
        showFlash(`Agregaste ${mentor.nombre} a tu equipo.`);
      }
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setPendingId(null);
    }
  }

  async function handleRemove(item: MyMentor) {
    if (pendingId !== null) return;
    const token = getToken();
    if (!token) return;
    const ok = window.confirm(
      `¿Quitar a ${item.mentor.nombre} de tu equipo? Podés volver a agregarlo desde el catálogo.`,
    );
    if (!ok) return;
    setError(null);
    setPendingId(item.mentor.id);
    try {
      const res = await fetch(`${API_URL}/users/me/mentors/${item.mentor.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok && res.status !== 204) {
        throw new Error(`HTTP ${res.status}`);
      }
      showFlash(`Quitaste a ${item.mentor.nombre} de tu equipo.`);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setPendingId(null);
    }
  }

  const teamCount = team?.length ?? 0;
  const catalogCount = catalog?.length ?? 0;

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-6 py-12">
        <div className="mx-auto w-full max-w-5xl">
          <header className="mb-8 border-b border-rule pb-6">
            <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              Tu equipo
            </p>
            <h1 className="mt-2 font-serif text-4xl font-medium tracking-tight text-ink">
              Mentores
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-ink-soft">
              Esta es la mesa de tu equipo. Acá ves quién está hoy con vos y
              explorás el catálogo para sumar más. Cualquier mentor del catálogo
              lo agregás al toque; cualquiera de tu equipo lo podés quitar
              cuando quieras.
            </p>
          </header>

          {/* Flash + error */}
          {flash && (
            <p className="animate-fade-in-up mb-4 rounded-lg border border-accent-soft bg-accent-soft px-4 py-2 text-sm text-accent">
              {flash}
            </p>
          )}
          {error && (
            <p className="mb-4 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
              {error}
            </p>
          )}

          {/* Tabs */}
          <div className="mb-6 flex items-center gap-1 border-b border-rule">
            <TabButton
              active={tab === "team"}
              onClick={() => setTab("team")}
              label="Mi equipo"
              count={team === null ? null : teamCount}
            />
            <TabButton
              active={tab === "catalog"}
              onClick={() => setTab("catalog")}
              label="Catálogo"
              count={catalog === null ? null : catalogCount}
            />
            <div className="ml-auto pb-2">
              <Link
                href="/dashboard"
                className="text-xs text-ink-soft underline-offset-2 hover:text-accent hover:underline"
              >
                ← Volver al dashboard
              </Link>
            </div>
          </div>

          {tab === "team" ? (
            <TeamSection
              items={team}
              pendingId={pendingId}
              onRemove={handleRemove}
            />
          ) : (
            <CatalogSection
              items={catalog}
              pendingId={pendingId}
              onAdd={handleAdd}
            />
          )}
        </div>
      </div>
    </AppShell>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TabButton({
  active,
  onClick,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number | null;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "relative -mb-px border-b-2 border-accent px-4 py-2 text-sm font-medium text-ink"
          : "relative -mb-px border-b-2 border-transparent px-4 py-2 text-sm text-ink-soft hover:text-ink"
      }
    >
      {label}
      {count !== null && (
        <span
          className={
            active
              ? "ml-2 rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-medium text-accent"
              : "ml-2 rounded-full bg-paper-dim px-2 py-0.5 text-[10px] font-medium text-ink-muted"
          }
        >
          {count}
        </span>
      )}
    </button>
  );
}

function TeamSection({
  items,
  pendingId,
  onRemove,
}: {
  items: MyMentor[] | null;
  pendingId: number | null;
  onRemove: (item: MyMentor) => void;
}) {
  if (items === null) return <SkeletonGrid />;
  if (items.length === 0) {
    return (
      <EmptyState
        title="Tu equipo está vacío"
        body="Empezá agregando mentores desde el catálogo o creando uno a medida desde el dashboard."
      />
    );
  }
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item, i) => (
        <div
          key={item.mentor.id}
          className="animate-fade-in-up"
          style={{ animationDelay: `${i * 40}ms` }}
        >
          <TeamCard
            item={item}
            pending={pendingId === item.mentor.id}
            disabled={pendingId !== null && pendingId !== item.mentor.id}
            onRemove={() => onRemove(item)}
          />
        </div>
      ))}
    </div>
  );
}

function CatalogSection({
  items,
  pendingId,
  onAdd,
}: {
  items: CatalogMentor[] | null;
  pendingId: number | null;
  onAdd: (mentor: CatalogMentor) => void;
}) {
  if (items === null) return <SkeletonGrid />;
  if (items.length === 0) {
    return (
      <EmptyState
        title="Ya tenés todos los mentores del catálogo"
        body="Si querés un oficio distinto, podés crear un mentor a medida con el Creador desde el dashboard."
      />
    );
  }
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((mentor, i) => (
        <div
          key={mentor.id}
          className="animate-fade-in-up"
          style={{ animationDelay: `${i * 40}ms` }}
        >
          <CatalogCard
            mentor={mentor}
            pending={pendingId === mentor.id}
            disabled={pendingId !== null && pendingId !== mentor.id}
            onAdd={() => onAdd(mentor)}
          />
        </div>
      ))}
    </div>
  );
}

function TeamCard({
  item,
  pending,
  disabled,
  onRemove,
}: {
  item: MyMentor;
  pending: boolean;
  disabled: boolean;
  onRemove: () => void;
}) {
  const { mentor, source, match_reason } = item;
  return (
    <article className="shadow-card flex h-full flex-col rounded-2xl border border-rule bg-paper-dim p-5 transition-all hover:border-rule-strong">
      <div className="flex items-start justify-between gap-2">
        <h2 className="font-serif text-2xl font-medium italic tracking-tight text-ink">
          {mentor.nombre}
        </h2>
        {sourceBadge(source)}
      </div>
      <p className="mt-1.5 text-[10px] uppercase tracking-[0.14em] text-ink-muted line-clamp-1">
        {mentor.canon}
      </p>
      <p className="mt-3 font-serif text-base italic leading-relaxed text-ink-soft line-clamp-3">
        {mentor.filosofia}
      </p>
      {match_reason && (
        <p className="mt-3 border-t border-rule pt-2 text-xs leading-5 text-ink line-clamp-3">
          {match_reason}
        </p>
      )}
      <div className="mt-auto flex gap-2 pt-4">
        <Link
          href="/dashboard"
          className="flex-1 rounded-xl border border-rule bg-paper px-3 py-2 text-center text-sm text-ink-soft hover:border-rule-strong hover:text-ink"
        >
          Hablar
        </Link>
        <button
          type="button"
          onClick={onRemove}
          disabled={pending || disabled}
          className="flex-1 rounded-xl border border-rule bg-paper px-3 py-2 text-sm text-ink-soft transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
        >
          {pending ? "Quitando..." : "Quitar"}
        </button>
      </div>
    </article>
  );
}

function CatalogCard({
  mentor,
  pending,
  disabled,
  onAdd,
}: {
  mentor: CatalogMentor;
  pending: boolean;
  disabled: boolean;
  onAdd: () => void;
}) {
  return (
    <article className="shadow-card hover:shadow-card-hover flex h-full flex-col rounded-2xl border border-rule bg-paper-dim p-5 transition-all hover:-translate-y-0.5 hover:border-rule-strong">
      <h2 className="font-serif text-2xl font-medium italic tracking-tight text-ink">
        {mentor.nombre}
      </h2>
      <p className="mt-1.5 text-[10px] uppercase tracking-[0.14em] text-ink-muted line-clamp-1">
        {mentor.canon}
      </p>
      <p className="mt-3 font-serif text-base italic leading-relaxed text-ink-soft line-clamp-4">
        {mentor.filosofia}
      </p>
      <button
        type="button"
        onClick={onAdd}
        disabled={pending || disabled}
        className="mt-auto rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-hover disabled:opacity-60"
        style={{ marginTop: "1rem" }}
      >
        {pending ? "Agregando..." : "+ Agregar a mi equipo"}
      </button>
    </article>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          className="h-56 animate-pulse-dot rounded-2xl border border-rule bg-paper-dim"
        />
      ))}
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-rule bg-paper-dim p-10 text-center">
      <p className="font-serif text-xl italic text-ink-soft">{title}</p>
      <p className="mx-auto mt-2 max-w-md text-sm text-ink-muted">{body}</p>
    </div>
  );
}
