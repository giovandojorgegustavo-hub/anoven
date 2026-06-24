/**
 * Chat con un mentor — main panel únicamente.
 *
 * Sidebar viene de AppShell. Esta página solo renderiza:
 *   - Header con info del mentor + project
 *   - Stream de mensajes con bubbles + attachments
 *   - Input con texto + upload + send
 *
 * SSE markers handled:
 *   - mentor_created (Promptifex pipeline output)
 *   - similar_mentor_found (dedup)
 *   - mentor_creation_failed
 *   - tool_started / tool_completed / tool_failed / tool_cap_reached (Phase 2 agentic tools)
 */

"use client";

import { use, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";
import { playReplyDoneSound } from "@/lib/sound";
import { AppShell } from "@/components/AppShell";
import { ContextWarning } from "@/components/ContextWarning";

type Mentor = {
  id: number;
  slug: string;
  nombre: string;
  canon: string;
  filosofia: string;
};

type Conversation = {
  id: number;
  mentor_id: number;
  use_case_id: number | null;
  title: string | null;
  created_at: string;
  updated_at: string;
  mentor: Mentor;
  message_count: number;
  project_name: string | null;
  use_case_name: string | null;
};

type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  attachment_urls?: string[];
  // Shared-project authorship (anoven-shared-projects batch 6)
  // author_user_id: NULL = turno del mentor; presente = quién escribió
  author_user_id?: number | null;
  // Only set when message belongs to a DIFFERENT member of the shared project
  author_email_redacted?: string | null;
};

type UploadedAttachment = {
  id: number;
  url: string;
  mime_type: string;
  size_bytes: number;
  page_count?: number | null;
  is_indexed?: boolean;
  indexing?: boolean;
  index_status?: string | null;
  index_progress?: string | null;
  index_error?: string | null;
};

// --- Phase 2: Tool activity state ---
// Tracks active tool executions during streaming. Keyed by tool_id (or fallback key).
type ToolActivityEntry =
  | { state: "started"; tool: string; inputPreview: string }
  | { state: "completed"; tool: string; durationMs: number; resultPreview: string }
  | { state: "failed"; tool: string; error: string };

type ToolActivities = Map<string, ToolActivityEntry>;

function MarkdownContent({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: (props) => <p className="mb-2 leading-6 last:mb-0" {...props} />,
        strong: (props) => <strong className="font-semibold" {...props} />,
        em: (props) => <em className="italic" {...props} />,
        h1: (props) => <h1 className="mt-3 mb-2 text-lg font-semibold" {...props} />,
        h2: (props) => <h2 className="mt-3 mb-2 text-base font-semibold" {...props} />,
        h3: (props) => <h3 className="mt-2 mb-1 text-base font-semibold" {...props} />,
        h4: (props) => <h4 className="mt-2 mb-1 text-sm font-semibold" {...props} />,
        ul: (props) => <ul className="mb-2 ml-5 list-disc space-y-1" {...props} />,
        ol: (props) => <ol className="mb-2 ml-5 list-decimal space-y-1" {...props} />,
        li: (props) => <li className="leading-6" {...props} />,
        blockquote: (props) => (
          <blockquote className="my-2 border-l-2 border-current/30 pl-3 italic opacity-80" {...props} />
        ),
        code: ({ className, children, ...rest }) => {
          const inline = !/^language-/.test(className || "");
          if (inline) {
            return (
              <code
                className="rounded bg-black/10 px-1 py-0.5 font-mono text-[0.875em]"
                {...rest}
              >
                {children}
              </code>
            );
          }
          return (
            <code className={className} {...rest}>
              {children}
            </code>
          );
        },
        pre: (props) => (
          <pre className="my-2 overflow-x-auto rounded-lg bg-black/10 p-3 font-mono text-xs" {...props} />
        ),
        a: (props) => (
          <a className="underline underline-offset-2 hover:opacity-80" target="_blank" rel="noopener noreferrer" {...props} />
        ),
        table: (props) => (
          <div className="my-2 overflow-x-auto">
            <table className="w-full border-collapse text-sm" {...props} />
          </div>
        ),
        th: (props) => <th className="border border-current/30 bg-black/5 px-2 py-1 text-left font-semibold" {...props} />,
        td: (props) => <td className="border border-current/30 px-2 py-1" {...props} />,
        hr: () => <hr className="my-3 border-current/30" />,
      }}
    >
      {children}
    </ReactMarkdown>
  );
}

export default function ChatPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const [conv, setConv] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [creatingNew, setCreatingNew] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<UploadedAttachment[]>([]);

  // Poll status de adjuntos que estan siendo indexados (PDFs >100 pag, RAG).
  useEffect(() => {
    const pending = pendingAttachments.filter((a) => a.indexing);
    if (pending.length === 0) return;
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    const tick = async () => {
      for (const att of pending) {
        try {
          const res = await fetch(`${API_URL}/attachments/${att.id}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) continue;
          const status = await res.json();
          if (cancelled) return;
          setPendingAttachments((prev) =>
            prev.map((a) =>
              a.id === att.id
                ? {
                    ...a,
                    indexing: status.indexing,
                    is_indexed: status.is_indexed,
                    page_count: status.page_count,
                    index_status: status.index_status,
                    index_progress: status.index_progress,
                    index_error: status.index_error,
                  }
                : a,
            ),
          );
        } catch {
          /* silent */
        }
      }
    };
    const t = setInterval(tick, 2000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [pendingAttachments]);
  const [uploading, setUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createdMentor, setCreatedMentor] = useState<
    { mentor_id: number; nombre: string; canon: string; filosofia: string } | null
  >(null);
  const [similarMentors, setSimilarMentors] = useState<
    Array<{ id: number; nombre: string; canon: string; filosofia: string }>
  >([]);
  type ContextStatus = {
    state: "warning" | "compacted" | null;
    utilization?: number;
    droppedCount?: number;
  };
  const [contextStatus, setContextStatus] = useState<ContextStatus>({ state: null });
  const [imageGen, setImageGen] = useState<
    | { state: "idle" }
    | { state: "generating" }
    | { state: "failed"; error: string }
  >({ state: "idle" });
  const [mentorCreating, setMentorCreating] = useState<
    | { state: "idle" }
    | { state: "generating" }
    | { state: "failed"; error: string }
  >({ state: "idle" });
  // Phase 2: tool activity pills — scoped to the in-progress assistant message only
  const [toolActivities, setToolActivities] = useState<ToolActivities>(new Map());
  const [toolCapReached, setToolCapReached] = useState<{ maxUses: number } | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // === Bootstrap: cargar conversación + mensajes ===
  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    (async () => {
      try {
        const [convRes, msgsRes] = await Promise.all([
          fetch(`${API_URL}/conversations/${id}`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${API_URL}/conversations/${id}/messages`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ]);
        if (convRes.status === 401) {
          clearToken();
          router.replace("/?error=session_expired");
          return;
        }
        if (convRes.status === 404) {
          router.replace("/dashboard?error=conversation_not_found");
          return;
        }
        if (!convRes.ok) throw new Error(`HTTP ${convRes.status}`);
        if (!msgsRes.ok) throw new Error(`/messages HTTP ${msgsRes.status}`);
        setConv(await convRes.json());
        setMessages(await msgsRes.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error");
      }
    })();
  }, [id, router]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    // Auto-scroll SOLO si el user ya esta cerca del bottom (a < 120px).
    // Si scrolleo para arriba a leer, NO lo molestamos forzando scroll.
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom < 120) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  async function handleUploadFile(file: File) {
    if (uploading || streaming) return;
    const token = getToken();
    if (!token) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      if (conv?.id) form.append("conversation_id", String(conv.id));
      const res = await fetch(`${API_URL}/attachments`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const att: UploadedAttachment = await res.json();
      setPendingAttachments((prev) => [...prev, att]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error subiendo imagen");
    } finally {
      setUploading(false);
    }
  }

  async function handleNewConversation() {
    if (!conv || creatingNew || streaming) return;
    const token = getToken();
    if (!token) return;
    setCreatingNew(true);
    try {
      const res = await fetch(`${API_URL}/conversations`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ mentor_id: conv.mentor_id, force_new: true }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const newConv: Conversation = await res.json();
      router.push(`/chat/${newConv.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
      setCreatingNew(false);
    }
  }

  async function handleDeleteCurrent() {
    if (!conv) return;
    if (!confirm("¿Borrar esta conversación con todos sus mensajes?")) return;
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/conversations/${conv.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    }
  }

  async function sendMessage() {
    if (!conv) return;
    const token = getToken();
    if (!token) return;
    const trimmed = input.trim();
    if ((!trimmed && pendingAttachments.length === 0) || streaming) return;

    const localUserId = -Date.now();
    const localAssistantId = -Date.now() - 1;
    const attachmentUrls = pendingAttachments.map((a) => a.url);
    setMessages((prev) => [
      ...prev,
      {
        id: localUserId,
        role: "user",
        content: trimmed,
        created_at: new Date().toISOString(),
        attachment_urls: attachmentUrls,
      },
      {
        id: localAssistantId,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
      },
    ]);
    const attachmentIds = pendingAttachments.map((a) => a.id);
    setInput("");
    setPendingAttachments([]);
    setContextStatus({ state: null });
    // Reset tool activity state for new turn
    setToolActivities(new Map());
    setToolCapReached(null);
    setStreaming(true);

    let accumulated = "";

    try {
      const res = await fetch(`${API_URL}/conversations/${conv.id}/messages`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ content: trimmed, attachment_ids: attachmentIds }),
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const ev of events) {
          if (!ev.trim()) continue;
          let eventType: string | null = null;
          let dataLine: string | null = null;
          for (const line of ev.split("\n")) {
            if (line.startsWith("event: ")) eventType = line.slice(7).trim();
            else if (line.startsWith("data: ")) dataLine = line.slice(6);
          }
          if (dataLine === null || dataLine === "[DONE]") continue;

          if (eventType === "mentor_creation_started") {
            setMentorCreating({ state: "generating" });
            continue;
          }
          if (eventType === "mentor_created") {
            try { setCreatedMentor(JSON.parse(dataLine)); } catch {}
            setMentorCreating({ state: "idle" });
            continue;
          }
          if (eventType === "similar_mentor_found") {
            try {
              const obj = JSON.parse(dataLine);
              setSimilarMentors(obj.existing ?? []);
            } catch {}
            continue;
          }
          if (eventType === "mentor_creation_failed") {
            setError("Promptifex no pudo armar el mentor. Iterá con el Creador.");
            setMentorCreating({ state: "failed", error: "Promptifex no pudo armar el mentor." });
            continue;
          }
          if (eventType === "ctx_warning") {
            try {
              const p = JSON.parse(dataLine);
              setContextStatus({ state: "warning", utilization: p.utilization });
            } catch {}
            continue;
          }
          if (eventType === "ctx_compacted") {
            try {
              const p = JSON.parse(dataLine);
              setContextStatus({ state: "compacted", droppedCount: p.messages_dropped });
            } catch {}
            continue;
          }
          if (eventType === "image_generation_started") {
            setImageGen({ state: "generating" });
            continue;
          }
          if (eventType === "image_generated") {
            try {
              const p = JSON.parse(dataLine);
              setMessages((prev) => {
                const copy = [...prev];
                const last = copy[copy.length - 1];
                if (last && last.role === "assistant") {
                  copy[copy.length - 1] = {
                    ...last,
                    attachment_urls: [...(last.attachment_urls ?? []), p.url],
                  };
                }
                return copy;
              });
              setImageGen({ state: "idle" });
            } catch {}
            continue;
          }
          if (eventType === "image_failed") {
            try {
              const p = JSON.parse(dataLine);
              setImageGen({ state: "failed", error: p.error ?? "Error desconocido" });
            } catch {
              setImageGen({ state: "failed", error: "Error desconocido" });
            }
            continue;
          }

          // --- Phase 2: agentic tool events ---
          // Tolerant receiver: unknown event types (including these before backend deploy)
          // are silently ignored — no crash, stream continues (SC-B3-01, SC-P2-08).
          if (eventType === "tool_started") {
            try {
              const p = JSON.parse(dataLine);
              const key: string = p.tool_id ?? `tool-${Date.now()}`;
              setToolActivities((prev) => {
                const next = new Map(prev);
                next.set(key, {
                  state: "started",
                  tool: p.tool ?? "herramienta",
                  inputPreview: p.input_preview ?? "",
                });
                return next;
              });
            } catch (e) {
              console.warn("[SSE] tool_started parse error — ignored", e);
            }
            continue;
          }
          if (eventType === "tool_completed") {
            try {
              const p = JSON.parse(dataLine);
              const key: string = p.tool_id ?? "";
              setToolActivities((prev) => {
                const next = new Map(prev);
                const existing = key ? prev.get(key) : null;
                const toolName = existing?.tool ?? p.tool ?? "herramienta";
                next.set(key || `done-${Date.now()}`, {
                  state: "completed",
                  tool: toolName,
                  durationMs: p.duration_ms ?? 0,
                  resultPreview: p.result_preview ?? "",
                });
                return next;
              });
            } catch (e) {
              console.warn("[SSE] tool_completed parse error — ignored", e);
            }
            continue;
          }
          if (eventType === "tool_failed") {
            try {
              const p = JSON.parse(dataLine);
              const key: string = p.tool_id ?? "";
              setToolActivities((prev) => {
                const next = new Map(prev);
                const existing = key ? prev.get(key) : null;
                const toolName = existing?.tool ?? p.tool ?? "herramienta";
                next.set(key || `failed-${Date.now()}`, {
                  state: "failed",
                  tool: toolName,
                  error: p.error ?? "Error desconocido",
                });
                return next;
              });
            } catch (e) {
              console.warn("[SSE] tool_failed parse error — ignored", e);
            }
            continue;
          }
          if (eventType === "tool_cap_reached") {
            try {
              const p = JSON.parse(dataLine);
              setToolCapReached({ maxUses: p.max_uses ?? 5 });
            } catch (e) {
              console.warn("[SSE] tool_cap_reached parse error — ignored", e);
            }
            continue;
          }
          // Tolerant receiver: any unrecognised named event is silently discarded (SC-B3-01).
          if (eventType !== null) {
            console.info("[SSE] unknown event type discarded:", eventType);
            continue;
          }

          try {
            const obj = JSON.parse(dataLine);
            if (typeof obj.text === "string") {
              accumulated += obj.text;
              setMessages((prev) => {
                const copy = [...prev];
                const last = copy[copy.length - 1];
                if (last && last.role === "assistant") {
                  copy[copy.length - 1] = { ...last, content: accumulated };
                }
                return copy;
              });
            }
          } catch {}
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const copy = [...prev];
        const last = copy[copy.length - 1];
        if (last && last.role === "assistant" && !last.content) {
          copy[copy.length - 1] = {
            ...last,
            content: "[Respuesta interrumpida — refrescá la página para reintentar.]",
          };
        }
        return copy;
      });
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setStreaming(false);
      // Clear tool activity pills when streaming ends
      setToolActivities(new Map());
      setToolCapReached(null);
      // If image generation pill stayed stuck (model never invoked tool or SSE missed event),
      // reset it so the user sees a clear final state.
      setImageGen((prev) => (prev.state === "generating" ? { state: "idle" } : prev));
      inputRef.current?.focus();
      // Sonido al terminar la respuesta (ding de 2 tonos).
      try {
        playReplyDoneSound();
      } catch {}
    }
  }

  return (
    <>
    {lightboxUrl && (
      <Lightbox url={lightboxUrl} onClose={() => setLightboxUrl(null)} />
    )}
    <AppShell activeConvId={Number(id)}>
      {!conv ? (
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Skeleton del chat mientras carga */}
          <div className="border-b border-rule bg-paper-dim px-6 py-4">
            <div className="mx-auto w-full max-w-5xl">
              <div className="h-2 w-32 animate-pulse-dot rounded bg-rule" />
              <div className="mt-2 h-6 w-48 animate-pulse-dot rounded bg-rule" />
              <div className="mt-2 h-2 w-64 animate-pulse-dot rounded bg-rule" />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-6 py-8">
            <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className={`flex ${i % 2 === 0 ? "justify-start" : "justify-end"}`}
                >
                  <div
                    className={`h-16 animate-pulse-dot rounded-2xl ${
                      i % 2 === 0 ? "w-[60%] bg-paper-dim" : "w-[50%] bg-rule"
                    }`}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex flex-1 flex-col overflow-hidden">
          <header className="border-b border-rule bg-paper-dim px-6 py-2">
            <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3">
              <div className="flex min-w-0 flex-1 items-baseline gap-3">
                <h1 className="truncate font-serif text-base font-medium text-ink">
                  {conv.title || "Nueva conversación"}
                </h1>
                <span className="shrink-0 rounded-md bg-paper px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider text-ink-soft">
                  {conv.mentor.nombre}
                </span>
                {conv.project_name && conv.use_case_name && (
                  <p className="truncate text-[11px] text-ink-muted">
                    · {conv.project_name} / {conv.use_case_name}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button
                  onClick={handleNewConversation}
                  disabled={creatingNew}
                  title="Nueva charla con este mentor"
                  className="rounded-md p-1.5 text-ink-soft hover:bg-paper hover:text-accent disabled:opacity-50"
                  aria-label="Nueva charla"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 5v14M5 12h14" />
                  </svg>
                </button>
                <button
                  onClick={handleDeleteCurrent}
                  title="Borrar conversación"
                  className="rounded-md p-1.5 text-ink-muted hover:bg-paper hover:text-accent"
                  aria-label="Borrar"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                    <path d="M10 11v6M14 11v6" />
                    <path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
              </div>
            </div>
          </header>

          <div ref={scrollerRef} className="flex-1 overflow-y-auto px-6 py-8">
            <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
              {error && (
                <p className="rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
                  {error}
                </p>
              )}
              {messages.length === 0 && (
                <div className="animate-fade-in-up rounded-xl border border-dashed border-rule bg-paper-dim p-8 text-center">
                  <p className="font-serif text-2xl italic text-ink">
                    {conv.mentor.nombre}
                  </p>
                  <p className="mt-2 text-xs uppercase tracking-[0.14em] text-ink-muted">
                    {conv.mentor.canon}
                  </p>
                  <p className="mt-4 font-serif text-base italic leading-relaxed text-ink-soft">
                    Esta charla todavía no empezó. Contale algo concreto y
                    arrancamos.
                  </p>
                </div>
              )}
              {messages.map((m, i) => (
                <div
                  key={m.id}
                  className="animate-fade-in-up"
                  style={{ animationDelay: m.id < 0 ? "0ms" : `${Math.min(i * 30, 200)}ms` }}
                >
                  <Bubble message={m} onImageClick={setLightboxUrl} />
                </div>
              ))}
              {streaming && messages[messages.length - 1]?.content === "" && (
                <p className="font-serif text-sm italic text-ink-muted">
                  escribiendo...
                </p>
              )}

              {/* Phase 2: Tool activity pills — shown inline during streaming only */}
              {streaming && toolActivities.size > 0 && (
                <div className="flex flex-col gap-1.5 pl-1">
                  {Array.from(toolActivities.entries()).map(([key, entry]) => (
                    <ToolActivityPill key={key} entry={entry} />
                  ))}
                </div>
              )}
              {streaming && toolCapReached && (
                <p className="text-[11px] italic text-ink-muted pl-1">
                  Límite de herramientas alcanzado ({toolCapReached.maxUses})
                </p>
              )}

              {createdMentor && (
                <div className="mt-4 rounded-xl border border-leaf bg-leaf-soft px-5 py-4">
                  <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                    Mentor creado
                  </p>
                  <h3 className="mt-1 font-serif text-2xl italic text-ink">
                    {createdMentor.nombre}
                  </h3>
                  <p className="mt-2 text-xs uppercase tracking-wide text-ink-muted">
                    {createdMentor.canon}
                  </p>
                  <p className="mt-3 font-serif text-base italic text-ink-soft">
                    {createdMentor.filosofia}
                  </p>
                  {similarMentors.length > 0 && (
                    <div className="mt-4 rounded-lg border border-rule bg-paper p-3">
                      <p className="text-[11px] uppercase tracking-wide text-ink-muted">
                        Mentores similares en el catálogo
                      </p>
                      <ul className="mt-2 space-y-1.5 text-sm text-ink-soft">
                        {similarMentors.map((s) => (
                          <li key={s.id}>
                            · <span className="font-serif italic">{s.nombre}</span>{" "}
                            — <span className="text-xs">{s.filosofia}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <Link
                    href="/dashboard"
                    className="mt-4 inline-flex w-full items-center justify-center rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink hover:bg-accent-hover"
                  >
                    Ver en el dashboard →
                  </Link>
                </div>
              )}
            </div>
          </div>

          <ContextWarning
            state={contextStatus.state}
            droppedCount={contextStatus.droppedCount}
            onDismiss={() => setContextStatus({ state: null })}
          />
          <footer className="border-t border-rule bg-paper-dim px-6 py-3">
            <div className="mx-auto w-full max-w-5xl">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  sendMessage();
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "copy";
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  const files = Array.from(e.dataTransfer.files).filter((f) =>
                    f.type.startsWith("image/") || f.type === "application/pdf" || f.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" || f.type === "application/msword",
                  );
                  files.forEach(handleUploadFile);
                }}
                className={`flex flex-col rounded-2xl border bg-paper transition-colors ${
                  isDragging
                    ? "border-accent ring-2 ring-accent/40"
                    : "border-rule focus-within:border-accent focus-within:ring-1 focus-within:ring-accent"
                }`}
              >
                {/* Previews adentro del contenedor */}
                {imageGen.state === "generating" && (
                  <div className="mb-2 flex items-center gap-2 rounded-lg border border-rule bg-paper-dim px-3 py-2 text-sm italic text-ink-muted">
                    <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true" />
                    <span>Generando imagen — puede tardar 5 a 15 segundos…</span>
                  </div>
                )}
                {mentorCreating.state === "generating" && (
                  <div className="mb-2 flex items-center gap-2 rounded-lg border border-leaf bg-leaf-soft px-3 py-2 text-sm italic text-ink">
                    <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true" />
                    <span>Armando tu mentor — esto puede tardar 10 a 30 segundos…</span>
                  </div>
                )}
                {imageGen.state === "failed" && (
                  <div className="mb-2 flex items-start justify-between gap-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
                    <span>No se pudo generar la imagen: {imageGen.error}</span>
                    <button
                      type="button"
                      onClick={() => setImageGen({ state: "idle" })}
                      className="shrink-0 text-xs underline"
                    >
                      cerrar
                    </button>
                  </div>
                )}
                {pendingAttachments.length > 0 && (
                  <div className="flex flex-wrap gap-2 border-b border-rule px-3 pb-2 pt-3">
                    {pendingAttachments.map((att) => {
                      const isPdf = att.mime_type === "application/pdf";
                      return (
                        <div
                          key={att.id}
                          className={`group relative ${isPdf ? "flex h-16 items-center gap-2 rounded-lg border border-rule px-3" : "h-16 w-16 overflow-hidden rounded-lg border border-rule"}`}
                        >
                          {isPdf ? (
                            <>
                              <span className="text-lg" aria-hidden>📄</span>
                              <span className="text-xs text-ink-soft">
                                {att.index_error ? (
                                  <span className="text-red-600">⚠ {att.index_error}</span>
                                ) : att.indexing ? (
                                  <span className="animate-pulse-dot">
                                    {att.index_status === "extracting" && "Abriendo PDF..."}
                                    {att.index_status === "chunking" && ('Procesando texto (' + (att.index_progress || '') + ')...')}
                                    {att.index_status === "embedding" && ('Indexando ' + (att.index_progress || '') + '...')}
                                    {att.index_status === "saving" && ('Guardando ' + (att.index_progress || '') + '...')}
                                    {!att.index_status && "Indexando PDF..."}
                                  </span>
                                ) : att.is_indexed ? (
                                  <>PDF listo ({att.page_count} pag, modo RAG)</>
                                ) : att.page_count ? (
                                  <>PDF ({att.page_count} pag)</>
                                ) : (
                                  <>PDF</>
                                )}
                              </span>
                            </>
                          ) : (
                            <img
                              src={`${API_URL}${att.url}`}
                              alt="adjunto"
                              className="h-full w-full object-cover"
                            />
                          )}
                          <button
                            type="button"
                            onClick={() =>
                              setPendingAttachments((prev) =>
                                prev.filter((a) => a.id !== att.id),
                              )
                            }
                            className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-ink/80 text-[10px] text-paper opacity-0 transition-opacity group-hover:opacity-100"
                            aria-label="Quitar"
                          >
                            ✕
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Textarea */}
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage();
                    }
                  }}
                  onPaste={(e) => {
                    const items = Array.from(e.clipboardData?.items ?? []);
                    const imageItems = items.filter((i) => i.type.startsWith("image/") || i.type === "application/pdf" || i.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" || i.type === "application/msword");
                    if (imageItems.length === 0) return;
                    e.preventDefault();
                    for (const item of imageItems) {
                      const file = item.getAsFile();
                      if (file) handleUploadFile(file);
                    }
                  }}
                  placeholder={
                    isDragging
                      ? "Soltá el archivo acá"
                      : `Escribile a ${conv.mentor.nombre}. Enter para enviar, Shift+Enter nueva línea.`
                  }
                  disabled={streaming}
                  rows={2}
                  className="w-full resize-none border-none bg-transparent px-4 py-3 text-sm text-ink placeholder:text-ink-muted outline-none disabled:opacity-60"
                />

                {/* Action bar abajo: 📎 a la izq, Enviar a la der */}
                <div className="flex items-center justify-between gap-2 px-3 pb-2">
                  <label
                    className="flex h-8 cursor-pointer items-center gap-1.5 rounded-lg px-2 text-xs text-ink-soft transition-colors hover:bg-paper-dim hover:text-accent"
                    title="Adjuntar imagen, PDF o Word (o arrastrá / pegá)"
                  >
                    {uploading ? (
                      <span className="animate-pulse-dot">subiendo...</span>
                    ) : (
                      <>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                        </svg>
                        Adjuntar
                      </>
                    )}
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp,image/gif,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword"
                      multiple
                      className="hidden"
                      disabled={uploading || streaming}
                      onChange={(e) => {
                        const files = Array.from(e.target.files ?? []);
                        files.forEach(handleUploadFile);
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <button
                    type="submit"
                    disabled={streaming || pendingAttachments.some((a) => a.indexing || a.index_error) || (!input.trim() && pendingAttachments.length === 0)}
                    className="rounded-lg bg-accent px-4 py-1.5 text-xs font-medium text-accent-ink transition-colors hover:bg-accent-hover disabled:opacity-40"
                  >
                    {streaming ? "Pensando..." : "Enviar ↵"}
                  </button>
                </div>
              </form>
            </div>
          </footer>
        </div>
      )}
    </AppShell>
    </>
  );
}

/**
 * Bubble — renders a single chat message.
 *
 * Shared-project authorship (anoven-shared-projects batch 6):
 * - If message.role === "assistant": shows mentor label above content.
 * - If message.author_email_redacted is set (message from ANOTHER member):
 *   shows a subtle terracotta badge with the redacted email (D3.1 compliant).
 *   The bubble background uses a warm paper tint to visually distinguish
 *   other-member messages (T3.15 — per-author diff, paper-tone variations only,
 *   NO new accent colors, D3.1/D3.2 safe).
 */
function Bubble({
  message,
  onImageClick,
}: {
  message: Message;
  onImageClick: (url: string) => void;
}) {
  const isUser = message.role === "user";
  const isOtherMember = isUser && !!message.author_email_redacted;
  const isMentor = message.role === "assistant";

  // Per-author visual diff (T3.15): other-member user bubbles get a slightly
  // warmer tint — bg-paper (default) instead of bg-ink, but still distinguished.
  // Uses existing design tokens only (D3.1: no new accent; D3.2: no dark: variants).
  let bubbleClass: string;
  if (isOtherMember) {
    // Another project member — warm paper with a terracotta-tinted left border
    bubbleClass = "max-w-[85%] rounded-2xl rounded-br-md border border-accent/25 bg-paper px-4 py-3 text-sm text-ink";
  } else if (isUser) {
    // Own user message — burbuja en mobile y desktop
    bubbleClass = "max-w-[85%] rounded-2xl rounded-br-md bg-ink px-4 py-3 text-sm text-paper";
  } else {
    // Mentor / assistant — full-width sin burbuja, fondo gris oscuro sutil (no rounded, no negro)
    bubbleClass = "w-full bg-ink/15 px-4 py-3 text-sm text-ink";
  }

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={bubbleClass}>
        {/* Mentor label for assistant turns */}
        {isMentor && (
          <p className="mb-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-ink-muted">
            Mentor
          </p>
        )}
        {/* Author badge for messages from OTHER project members (T3.13, D3.1) */}
        {isOtherMember && (
          <p
            title={message.author_email_redacted ?? undefined}
            className="mb-1.5 inline-flex items-center gap-1 rounded-sm bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-accent"
          >
            <span aria-hidden="true">●</span>
            {message.author_email_redacted}
          </p>
        )}
        {message.attachment_urls && message.attachment_urls.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {message.attachment_urls.map((url) => (
              <button
                key={url}
                type="button"
                onClick={() => onImageClick(`${API_URL}${url}`)}
                className="group relative h-20 w-20 overflow-hidden rounded-lg transition-transform hover:scale-105"
                aria-label="Ver imagen"
              >
                <img
                  src={`${API_URL}${url}`}
                  alt="adjunto"
                  className="h-full w-full object-cover"
                />
                <span className="absolute inset-0 flex items-center justify-center bg-ink/0 text-paper opacity-0 transition-all group-hover:bg-ink/30 group-hover:opacity-100">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
                  </svg>
                </span>
              </button>
            ))}
          </div>
        )}
        {message.content && (
          <div className="leading-6"><MarkdownContent>{message.content}</MarkdownContent></div>
        )}
      </div>
    </div>
  );
}

// --- Phase 2: ToolActivityPill ---
// Renders tool execution status inline near the streaming assistant bubble.
// Consistent with the imageGen pill style (paper/ink/accent terracotta design system).
function ToolActivityPill({ entry }: { entry: ToolActivityEntry }) {
  const toolLabel: Record<string, string> = {
    mem_search: "memoria",
    mem_save: "insight",
    generate_image: "imagen",
    web_search: "web",
  };
  const label = toolLabel[entry.tool] ?? entry.tool;

  if (entry.state === "started") {
    return (
      <div className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent-soft px-3 py-1 text-xs italic text-accent">
        <span
          className="inline-block h-2.5 w-2.5 animate-spin rounded-full border-2 border-current border-t-transparent"
          aria-hidden="true"
        />
        <span>
          {entry.tool === "mem_search" && "Buscando en memoria…"}
          {entry.tool === "mem_save" && "Guardando insight…"}
          {entry.tool === "generate_image" && "Generando imagen…"}
          {entry.tool === "web_search" && "Buscando en internet…"}
          {!["mem_search", "mem_save", "generate_image", "web_search"].includes(entry.tool) &&
            `Ejecutando ${label}…`}
        </span>
      </div>
    );
  }

  if (entry.state === "completed") {
    const durationText = entry.durationMs > 0 ? ` (${entry.durationMs}ms)` : "";
    return (
      <div className="inline-flex items-center gap-1.5 rounded-full border border-rule bg-paper-dim px-3 py-1 text-xs text-ink-muted">
        <span aria-hidden="true">✓</span>
        <span>
          {entry.tool === "mem_search" &&
            `Memoria consultada${entry.resultPreview ? ` — ${entry.resultPreview}` : ""}${durationText}`}
          {entry.tool === "mem_save" && `Insight guardado${durationText}`}
          {entry.tool === "generate_image" && `Imagen generada${durationText}`}
          {entry.tool === "web_search" && "Búsqueda completada"}
          {!["mem_search", "mem_save", "generate_image", "web_search"].includes(entry.tool) &&
            `${label} completado${durationText}`}
        </span>
      </div>
    );
  }

  // failed state
  return (
    <div className="inline-flex items-center gap-1.5 rounded-full border border-rule bg-paper-dim px-3 py-1 text-xs text-ink-muted">
      <span aria-hidden="true">—</span>
      <span>
        {entry.tool === "mem_search" && "Memoria no disponible — sigo igual"}
        {entry.tool === "mem_save" && "No se pudo guardar — sigo igual"}
        {entry.tool === "generate_image" && "No se pudo generar imagen"}
        {entry.tool === "web_search" && "Búsqueda falló — sigo igual"}
        {!["mem_search", "mem_save", "generate_image", "web_search"].includes(entry.tool) &&
          `${label} no disponible — sigo igual`}
      </span>
    </div>
  );
}

function Lightbox({ url, onClose }: { url: string; onClose: () => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/85 p-4 backdrop-blur-sm"
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Cerrar"
        className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-full bg-paper/10 text-paper transition-colors hover:bg-paper/20"
      >
        ✕
      </button>
      <img
        src={url}
        alt="imagen maximizada"
        onClick={(e) => e.stopPropagation()}
        className="max-h-full max-w-full rounded-lg object-contain shadow-2xl"
      />
    </div>
  );
}
