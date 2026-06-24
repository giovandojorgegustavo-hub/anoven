/**
 * Página `/onboarding` — chat con el Entrevistador.
 *
 * Flujo:
 *  1. Bootstrap: POST /interviews/start → obtenemos el attempt.
 *  2. GET /interviews/{id}/messages → traemos los mensajes existentes
 *     (incluye el saludo inicial del Entrevistador).
 *  3. User escribe → POST /interviews/{id}/messages con SSE response.
 *  4. Parseamos el stream `data: {...}\n\n` chunk por chunk y vamos
 *     appendendo el texto a la última bubble del assistant.
 *
 * El marker `[INTERVIEW_COMPLETE]` ya puede aparecer en las respuestas
 * (el system prompt lo conoce) pero NO lo procesamos en Sesión 2.2 —
 * eso viene en 2.3 (PostMessageHandler). Por ahora se muestra como texto.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";

// ============================================================
// Tipos
// ============================================================

type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

type Attempt = {
  id: number;
  status: string;
};

type MatchedMentor = {
  slug: string;
  nombre: string;
  reason: string;
};

type EvaluationResult = {
  score: number;
  highlights: string[];
  matched_mentors: MatchedMentor[];
};

// ============================================================
// Componente principal
// ============================================================

export default function OnboardingPage() {
  const router = useRouter();
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [interviewComplete, setInterviewComplete] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // === Bootstrap al montar ===
  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }

    (async () => {
      try {
        const startRes = await fetch(`${API_URL}/interviews/start`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        if (startRes.status === 401) {
          clearToken();
          router.replace("/?error=session_expired");
          return;
        }
        if (startRes.status === 409) {
          router.replace("/dashboard");
          return;
        }
        if (!startRes.ok) throw new Error(`/start HTTP ${startRes.status}`);
        const a: Attempt = await startRes.json();
        setAttempt(a);

        // Si el attempt ya pasó del chat (marker emitido), saltamos la
        // carga de mensajes y disparamos el Evaluador. El endpoint es
        // idempotente: si ya está 'evaluated' devuelve el resultado guardado
        // sin re-cobrar Anthropic.
        if (a.status === "completed" || a.status === "evaluated") {
          setInterviewComplete(true);
          return;
        }

        const msgsRes = await fetch(
          `${API_URL}/interviews/${a.id}/messages`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!msgsRes.ok) throw new Error(`/messages HTTP ${msgsRes.status}`);
        const msgs: Message[] = await msgsRes.json();
        setMessages(msgs);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error desconocido");
      }
    })();
  }, [router]);

  // === Auto-scroll cuando llegan mensajes nuevos ===
  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  // === Auto-fire del Evaluador cuando se completa la entrevista ===
  // Se ejecuta una sola vez: cuando interviewComplete pasa a true.
  useEffect(() => {
    if (!interviewComplete || !attempt || evaluating || evaluation) return;
    const token = getToken();
    if (!token) return;

    setEvaluating(true);
    fetch(`${API_URL}/interviews/${attempt.id}/evaluate`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: EvaluationResult = await res.json();
        setEvaluation(data);
      })
      .catch((err) => {
        setError(
          err instanceof Error
            ? `Evaluación falló: ${err.message}`
            : "Evaluación falló",
        );
      })
      .finally(() => setEvaluating(false));
  }, [interviewComplete, attempt, evaluating, evaluation]);

  // === Enviar mensaje ===
  async function sendMessage() {
    if (!attempt) return;
    const token = getToken();
    if (!token) return;

    const trimmed = input.trim();
    if (!trimmed || streaming) return;

    // Optimistic: agregamos el mensaje del user inmediatamente +
    // una bubble vacía del assistant que vamos a ir llenando con el stream.
    const localUserId = -Date.now();
    const localAssistantId = -Date.now() - 1;
    setMessages((prev) => [
      ...prev,
      {
        id: localUserId,
        role: "user",
        content: trimmed,
        created_at: new Date().toISOString(),
      },
      {
        id: localAssistantId,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
      },
    ]);
    setInput("");
    setStreaming(true);

    let accumulated = "";

    try {
      const res = await fetch(
        `${API_URL}/interviews/${attempt.id}/messages`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ content: trimmed }),
        },
      );

      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE: cada evento termina en doble newline. Cada evento puede tener
        // varias líneas:  "event: <name>\ndata: <json>"  o solo  "data: <json>".
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const ev of events) {
          if (!ev.trim()) continue;

          let eventType: string | null = null;
          let dataLine: string | null = null;
          for (const line of ev.split("\n")) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              dataLine = line.slice(6);
            }
          }

          if (dataLine === null) continue;
          if (dataLine === "[DONE]") continue;

          // Evento especial: el Entrevistador cerró la entrevista.
          if (eventType === "interview_complete") {
            setInterviewComplete(true);
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
          } catch {
            // ignoramos eventos malformados
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      setStreaming(false);
      inputRef.current?.focus();
    }
  }

  function handleLogout() {
    clearToken();
    router.replace("/");
  }

  // === Render ===
  if (error) {
    return (
      <main className="flex flex-1 items-center justify-center px-6">
        <p className="font-serif text-lg italic text-accent">Error: {error}</p>
      </main>
    );
  }

  if (attempt === null) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="font-serif text-lg italic text-ink-soft">
          Preparando tu entrevista...
        </p>
      </main>
    );
  }

  return (
    <main className="flex flex-1 flex-col min-h-0">
      <header className="border-b border-rule bg-paper-dim px-6 py-4">
        <div className="mx-auto flex w-full max-w-2xl items-center justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
              Onboarding · intento #{attempt.id}
            </p>
            <h1 className="font-serif text-2xl font-medium italic text-ink">
              Entrevistador
            </h1>
          </div>
          <button
            onClick={handleLogout}
            className="text-sm text-ink-soft underline-offset-4 hover:text-accent hover:underline"
          >
            Cerrar sesión
          </button>
        </div>
      </header>

      <div ref={scrollerRef} className="flex-1 overflow-y-auto px-6 py-8">
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
          {messages.map((m) => (
            <Bubble key={m.id} message={m} />
          ))}
          {streaming && messages[messages.length - 1]?.content === "" && (
            <p className="font-serif text-sm italic text-ink-muted">
              escribiendo...
            </p>
          )}

          {interviewComplete && evaluating && (
            <div className="rounded-xl border border-rule bg-paper px-5 py-4">
              <p className="font-serif text-lg italic text-ink">
                Procesando tu perfil...
              </p>
              <p className="mt-1 text-sm text-ink-soft">
                Estamos extrayendo lo que mencionaste para armarte el equipo
                de mentores. Esto tarda unos segundos.
              </p>
            </div>
          )}

          {interviewComplete && evaluation && (
            <>
              <div className="rounded-xl border border-leaf bg-leaf-soft px-5 py-4">
                <p className="font-serif text-lg italic text-ink">
                  Listo, tu perfil está armado.
                </p>
                <ul className="mt-3 space-y-1.5 text-sm text-ink">
                  {evaluation.highlights.map((h, i) => (
                    <li key={i} className="flex gap-2">
                      <span aria-hidden className="text-leaf">·</span>
                      <span>{h}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {evaluation.matched_mentors.length > 0 && (
                <div className="rounded-xl border border-rule bg-paper p-5">
                  <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                    Tu equipo
                  </p>
                  <p className="font-serif text-lg italic text-ink">
                    5 mentores para arrancar
                  </p>
                  <ul className="mt-4 space-y-3">
                    {evaluation.matched_mentors.map((m) => (
                      <li
                        key={m.slug}
                        className="rounded-lg border border-rule bg-paper-dim p-4"
                      >
                        <p className="font-serif text-base font-medium text-ink">
                          {m.nombre}
                        </p>
                        {m.reason && (
                          <p className="mt-1.5 font-serif text-sm italic leading-relaxed text-ink-soft">
                            {m.reason}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          {interviewComplete && !evaluating && !evaluation && (
            <div className="rounded-xl border border-rule bg-paper px-5 py-4 font-serif text-base italic text-ink-soft">
              Entrevista finalizada.
            </div>
          )}
        </div>
      </div>

      <footer className="border-t border-rule bg-paper-dim px-6 py-4">
        {interviewComplete ? (
          <div className="mx-auto w-full max-w-2xl">
            <button
              onClick={() => router.push("/dashboard")}
              disabled={!evaluation}
              className="w-full rounded-xl bg-accent px-5 py-3 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-hover disabled:opacity-40"
            >
              {evaluating ? "Procesando..." : "Ir al dashboard"}
            </button>
          </div>
        ) : (
          <form
            className="mx-auto flex w-full max-w-2xl items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              sendMessage();
            }}
          >
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
              placeholder="Escribí tu respuesta. Enter para enviar, Shift+Enter para nueva línea."
              disabled={streaming}
              rows={2}
              className="flex-1 resize-none rounded-xl border border-rule bg-paper px-4 py-3 text-sm text-ink placeholder:text-ink-muted outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={streaming || !input.trim()}
              className="rounded-xl bg-accent px-5 py-3 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-hover disabled:opacity-40"
            >
              Enviar
            </button>
          </form>
        )}
      </footer>
    </main>
  );
}

// ============================================================
// Bubble
// ============================================================

function Bubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={
          isUser
            ? "max-w-[80%] rounded-2xl rounded-br-md bg-ink px-4 py-3 text-sm text-paper"
            : "max-w-[80%] rounded-2xl rounded-bl-md border border-rule bg-paper-dim px-4 py-3 text-sm text-ink"
        }
      >
        <p className="whitespace-pre-wrap leading-6">{message.content}</p>
      </div>
    </div>
  );
}
